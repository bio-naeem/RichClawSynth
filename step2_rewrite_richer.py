#!/usr/bin/env python3
"""
Experimental step2 rewrite that preserves more task complexity.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from pipeline_common import (
    OpenAICompatClient,
    add_openai_client_args,
    append_jsonl,
    build_openai_client_from_args,
    call_with_retries,
    is_transient_llm_error,
    load_jsonl,
    load_project_dotenv,
    require_api_key,
)

EXP_ROOT = Path(__file__).resolve().parent
from prompts_step2_exp import STEP2_EXP_RICH_USER_PROMPT_TEMPLATE, STEP2_EXP_SYSTEM_PROMPT  # noqa: E402


load_project_dotenv()

class RewrittenQueryValidationError(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Experimental richer step2 rewrite under gpt-exp.")
    parser.add_argument("input_jsonl", help="input step1 JSONL")
    parser.add_argument("output_jsonl", help="output rewritten JSONL")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=2)
    add_openai_client_args(parser, include_timeout=True)
    return parser.parse_args()


def compact_text(text: str, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，,；;：: ") + "..."


def build_hidden_plan_block(hidden_plan: list[str]) -> str:
    if not hidden_plan:
        return "- 无"
    return "\n".join(f"- {compact_text(step, 160)}" for step in hidden_plan)


def build_simple_block(values: list[str]) -> str:
    if not values:
        return "- 无"
    return "\n".join(f"- {compact_text(value, 160)}" for value in values)


def build_delivery_layers_block(layers: list[dict]) -> str:
    if not layers:
        return "- 无"
    rows = []
    for row in layers:
        layer = str(row.get("layer", "")).strip() or "layer"
        goal = str(row.get("goal", "")).strip() or "未提供"
        rows.append(f"- {layer}: {compact_text(goal, 180)}")
    return "\n".join(rows)


REVIEW_POINT_KEYWORDS = [
    "价格", "金额", "费率", "利率", "报价", "费用", "日期", "时间", "截止日期", "时效",
    "材料项", "材料", "名单", "规则", "门槛", "条件", "数字", "参数", "成分", "型号",
    "适用阶段", "负债金额", "逾期次数", "评分", "税费", "合约期", "带宽", "速率",
]
HIGH_RISK_REVIEW_TOPIC_KEYWORDS = [
    "申请", "办理", "核验", "真伪", "报销", "补贴", "价格", "报价", "资费",
    "利率", "金额", "日期", "材料", "合同", "征信", "理赔", "收费标准",
]
DECISION_HEAVY_KEYWORDS = ["对比", "参数", "选购", "推荐", "筛选", "资费", "报价", "落地价", "利率"]
EXECUTION_HEAVY_KEYWORDS = ["申请", "办理", "材料", "流程", "报销", "迁移", "登记", "核验"]
EVIDENCE_HEAVY_KEYWORDS = ["核验", "真伪", "规则", "价格", "金额", "时效", "日期", "合同", "征信", "理赔"]


def infer_review_points(topic: str, hidden_plan: list[str], kind: str) -> list[str]:
    text = "\n".join(hidden_plan)
    found = []
    for keyword in REVIEW_POINT_KEYWORDS:
        if keyword in text or keyword in topic:
            found.append(keyword)
    ordered = []
    seen = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    if ordered:
        return ordered[:4]
    if kind == "source_check_support":
        return ["来源是否可靠", "规则门槛是否属实", "关键字段是否匹配"]
    if kind == "analysis_with_evidence_check":
        return ["关键结论是否有依据支撑", "日期或材料项是否对应正确", "核心数字是否引用准确"]
    return []


def allow_review_requirement(topic: str, hidden_plan: list[str], kind: str) -> bool:
    if kind in {"source_check_support", "analysis_with_evidence_check"}:
        return True
    text = "\n".join(hidden_plan)
    if any(keyword in topic or keyword in text for keyword in HIGH_RISK_REVIEW_TOPIC_KEYWORDS):
        return bool(infer_review_points(topic, hidden_plan, kind))
    return False


LOCATION_SENSITIVE_KEYWORDS = [
    "资费", "价格", "报价", "收费标准", "运费", "时效", "路线", "路况", "限行", "补贴",
    "办理", "报销", "医院", "科室", "接种点", "门票", "客流量", "宽带", "落地价", "物业费",
    "学区", "政策", "公告", "停水", "停电", "租车", "理赔", "培训补贴", "年检", "迁移", "登记",
]


def location_policy(topic: str, persona_hint: str) -> str:
    if not persona_hint:
        return "如果地点不影响任务边界，就不要硬塞位置信息。"
    if any(keyword in topic for keyword in LOCATION_SENSITIVE_KEYWORDS):
        return "这个 topic 明显受地区影响。若 persona_hint 里含有城市或常住地，请自然把地点写进最终 query，用来限定政策、价格、渠道、规则、资费或服务范围。"
    return "只有在地点真的会影响规则、价格、渠道、服务范围或结果判断时，才自然吸收 persona_hint 里的位置信息；否则不要强行加地点。"


def persona_usage_policy(topic: str) -> str:
    if any(keyword in topic for keyword in DECISION_HEAVY_KEYWORDS):
        return "这是决策型任务。只有当 persona 信息会改变取舍标准、推荐优先级或风险偏好时，才自然吸收；不要把家庭情况或身份标签机械挂进 query。"
    if any(keyword in topic for keyword in EXECUTION_HEAVY_KEYWORDS):
        return "这是执行型任务。可以吸收 persona 里会影响结果使用方式的信息，例如是否希望直接照着办、是否需要更省心，但不要硬塞与任务无关的家庭或身份标签。"
    return "只有当 persona 信息真的会改变筛选标准、使用方式或结果形态时，才吸收进 query；否则宁可不用，也不要为了人设而人设。"


def build_extra_requirement_candidates(topic: str, persona_hint: str, hidden_plan: list[str], kind: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    if any(keyword in topic for keyword in DECISION_HEAVY_KEYWORDS):
        candidates.append(
            {
                "type": "decision_constraint",
                "content": "可以补一句真正会影响取舍标准或推荐优先级的现实限制，但前提是它和当前 topic 强相关。",
                "reason": "这类任务天然需要更明确的决策标准。",
            }
        )
    if any(keyword in topic for keyword in EXECUTION_HEAVY_KEYWORDS):
        candidates.append(
            {
                "type": "usage_context",
                "content": "可以补一句会影响结果怎么被使用的现实场景，例如是否需要直接照着办、是否要减少反复确认。",
                "reason": "这类任务更需要交付方式贴合用户执行场景。",
            }
        )
    elif any(keyword in topic for keyword in DECISION_HEAVY_KEYWORDS):
        candidates.append(
            {
                "type": "usage_context",
                "content": "可以补一句结果将如何被快速使用，例如拿来自己拍板、发给家人商量或快速对比，但前提是和当前 topic 自然匹配。",
                "reason": "这类任务通常存在后续决策使用场景。",
            }
        )
    if allow_review_requirement(topic, hidden_plan, kind):
        points = infer_review_points(topic, hidden_plan, kind)
        if points:
            candidates.append(
                {
                    "type": "review_point",
                    "content": "如需复核，只能落到这些具体点：" + "、".join(points),
                    "reason": "这是高风险或明确核查型任务，允许少量具体复核点。",
                }
            )
    return candidates[:3]


def extra_requirement_policy(topic: str, persona_hint: str, hidden_plan: list[str], kind: str) -> str:
    allow_review = allow_review_requirement(topic, hidden_plan, kind)
    if allow_review:
        return (
            "你可以补充 1 到 2 条合理需求，但默认优先 decision_constraint 和 usage_context。"
            "只有在确有必要时才允许补 review_point，而且必须具体。"
        )
    return (
        "你可以补充 1 到 2 条合理需求，但只优先使用 decision_constraint 和 usage_context。"
        "这条样本默认不要新增 review_point，也不要补泛化复核句。"
    )


def build_extra_requirement_block(topic: str, persona_hint: str, hidden_plan: list[str], kind: str) -> str:
    rows = build_extra_requirement_candidates(topic, persona_hint, hidden_plan, kind)
    if not rows:
        return "- 无"
    return "\n".join(
        f"- type={row['type']} | content={row['content']} | reason={row['reason']}" for row in rows
    )


def infer_main_delivery_hint(rec: dict, hidden_plan: list[str]) -> str:
    text = "\n".join(hidden_plan)
    match = re.search(r"核心交付为([^，。；]+)", text)
    if match:
        return match.group(1).strip()
    chain_design = rec.get("chain_design", {}) if isinstance(rec.get("chain_design"), dict) else {}
    primary = chain_design.get("primary_chain", [])
    if primary:
        last = primary[-1]
        slug = str(last.get("slug", "")).strip()
        if slug:
            return slug
    return "未明确"


def secondary_chain_guidance(kind: str) -> str:
    mapping = {
        "refinement_for_decision": (
            "- 这类副链的重点是把零散信息压成更利于做决定的表达。\n"
            "- 更适合写成“帮我理清楚重点、给我可直接决策的版本”。\n"
            "- 不要默认扩写成“多个交付物前后口径一致”。\n"
            "- 如果有表格、图表、文档并存，优先强调它们分别承担什么用途，而不是强调彼此对齐。"
        ),
        "presentation_support": (
            "- 这类副链的重点是补阅读体验、展示方式或更适合快速浏览的表达。\n"
            "- 更适合写成“再给我一版更直观/更好读/更方便转发的版本”。\n"
            "- 不要把它写成复核链，不要默认强调一致性检查。"
        ),
        "source_check_support": (
            "- 这类副链的重点是核来源、核规则、核字段，不是做全局一致性检查。\n"
            "- 如果保留核查要求，必须具体到来源是否可靠、规则门槛是否属实、关键字段是否匹配。\n"
            "- 不要泛泛地写成“前后口径一致”或“别自相矛盾”。"
        ),
        "analysis_with_evidence_check": (
            "- 这类副链的重点是判断结论是否真的被依据支撑。\n"
            "- 更适合写成“推荐结论要和证据、日期、材料项、关键数字对应得上”。\n"
            "- 不要把重点放在多个交付物互相对齐上。"
        ),
        "publish_support": (
            "- 这类副链的重点是把主结果收束成可发送、可转发、可对外展示的版本。\n"
            "- 更适合写成“基于主结果再整理一版能直接发给别人看的版本”。\n"
            "- 除非 hidden_plan 明确要求，否则不要默认补一句“报告和展示版必须完全一致”。\n"
            "- 重点描述这版内容更短、更直观、更适合转发，而不是强调它与主报告逐项对齐。"
        ),
    }
    return mapping.get(kind, "- 按单一用户目标改写，不要把副链默认写成泛化复核。")


def review_policy(topic: str, hidden_plan: list[str], kind: str) -> str:
    points = infer_review_points(topic, hidden_plan, kind)
    if not points:
        return "这条样本没有明确复核点。默认不要显式写“核对/一致/口径/对不上”这类句子，把这部分留给执行智能体隐含处理。"
    return "只有在必要时才保留复核要求；如果保留，请明确落到这些复核点：" + "、".join(points)


def build_prompt(rec: dict) -> str:
    chain_design = rec.get("chain_design", {}) if isinstance(rec.get("chain_design"), dict) else {}
    hidden_plan = [str(step).strip() for step in rec.get("hidden_plan", []) if str(step).strip()]
    kind = str(chain_design.get("secondary_chain_kind", "")).strip() or "未提供"
    enhancement_kind = str(chain_design.get("enhancement_chain_kind", "")).strip() or "未提供"
    persona_hint = str(rec.get("persona_hint", "")).strip() or "无"
    topic = str(rec.get("topic", "")).strip() or "未提供"
    input_context = str(rec.get("input_context", "")).strip() or "public_only"
    input_material_hint = str(rec.get("input_material_hint", "")).strip() or "无"
    global_constraints = [str(item).strip() for item in rec.get("global_constraints", []) if str(item).strip()]
    delivery_layers = rec.get("delivery_layers", []) if isinstance(rec.get("delivery_layers"), list) else []
    return STEP2_EXP_RICH_USER_PROMPT_TEMPLATE.format(
        persona_hint=persona_hint,
        topic=topic,
        input_context=input_context,
        input_material_hint=input_material_hint,
        template=str(chain_design.get("template", "")).strip() or "未提供",
        template_description=str(chain_design.get("template_description", "")).strip() or "未提供",
        main_delivery_hint=infer_main_delivery_hint(rec, hidden_plan),
        secondary_chain_kind=kind,
        enhancement_chain_kind=enhancement_kind,
        global_constraints=build_simple_block(global_constraints),
        delivery_layers=build_delivery_layers_block(delivery_layers),
        secondary_chain_guidance=secondary_chain_guidance(kind),
        review_policy=review_policy(topic, hidden_plan, kind),
        location_policy=location_policy(topic, persona_hint),
        persona_usage_policy=persona_usage_policy(topic),
        extra_requirement_policy=extra_requirement_policy(topic, persona_hint, hidden_plan, kind),
        extra_requirement_candidates=build_extra_requirement_block(topic, persona_hint, hidden_plan, kind),
        relative_paths_block="- 无",
        hidden_plan_block=build_hidden_plan_block(hidden_plan),
    )


def is_transient_error(exc: Exception) -> bool:
    return is_transient_llm_error(exc, extra_retryable=(RewrittenQueryValidationError,))


def build_output_record(original: dict, rewritten_query: str) -> dict:
    out = dict(original)
    out["query"] = rewritten_query
    ordered = {}
    for key in ("id", "topic", "persona_hint", "input_context", "input_material_hint", "hidden_plan", "query", "chain_design", "chain_skills"):
        if key in out:
            ordered[key] = out[key]
    for key, value in out.items():
        if key not in ordered:
            ordered[key] = value
    return ordered

def rewrite_record(rec: dict, retries: int, client: OpenAICompatClient) -> dict:
    return call_with_retries(
        lambda: _rewrite_record_once(rec, client),
        retries=retries,
        is_retryable=is_transient_error,
    )


def _rewrite_record_once(rec: dict, client: OpenAICompatClient) -> dict:
    rewritten_query = client.chat_text(
        STEP2_EXP_SYSTEM_PROMPT,
        build_prompt(rec),
    ).strip()
    rewritten_query = re.sub(r"\s+", " ", rewritten_query).strip()
    if len(rewritten_query) < 24:
        raise RewrittenQueryValidationError("rewritten query too short")
    return build_output_record(rec, rewritten_query)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_jsonl)
    output_path = Path(args.output_jsonl)
    records = load_jsonl(input_path)
    require_api_key(args.api_key)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("", encoding="utf-8")
    client = build_openai_client_from_args(args, max_retries=max(1, args.retries + 1))

    rewritten_records: list[dict] = []
    write_lock = Lock()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(rewrite_record, rec, args.retries, client): rec for rec in records}
        for future in as_completed(futures):
            rec = futures[future]
            result = future.result()
            rewritten_records.append(result)
            append_jsonl(output_path, result, write_lock)
            print(f"[ok] {rec.get('id', 'unknown')}", file=sys.stderr)

    print(json.dumps({"output_path": str(output_path), "count": len(rewritten_records)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
