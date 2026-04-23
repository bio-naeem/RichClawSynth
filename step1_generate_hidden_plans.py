#!/usr/bin/env python3
"""
Experimental step1 generator built on top of the new incremental step0 shards.

Outputs JSONL records similar to the original step1 format, but sampled from
role skeletons instead of a monolithic compatibility graph.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Any

from pipeline_common import (
    OpenAICompatClient,
    add_openai_client_args,
    append_jsonl,
    build_openai_client_from_args,
    call_with_retries,
    is_transient_llm_error,
    load_json,
    load_project_dotenv,
    require_api_key,
)

load_project_dotenv()


EXP_ROOT = Path(__file__).resolve().parent
CONFIG_ROOT = EXP_ROOT / "config"
ARTIFACTS_ROOT = EXP_ROOT / "artifacts"
OUTPUTS_ROOT = EXP_ROOT / "outputs"
TOPICS_PATH = EXP_ROOT / "references" / "topics_narrowed.txt"
TOPIC_TAXONOMY = load_json(CONFIG_ROOT / "topic_taxonomy.json")
FILE_DEPENDENCY_TOPIC_KEYWORDS = TOPIC_TAXONOMY["file_dependency_topic_keywords"]
EXTRACT_FRIENDLY_KEYWORDS = set(TOPIC_TAXONOMY["extract_friendly_keywords"])


def default_personas_path() -> Path:
    configured = os.environ.get("PERSONAS_PATH", "").strip()
    if configured:
        return Path(configured)
    local = EXP_ROOT / "references" / "user_scenarios.jsonl"
    if local.exists():
        return local
    return EXP_ROOT.parent / "references" / "user_scenarios.jsonl"


PERSONAS_PATH = default_personas_path()


def load_topics(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_topic_schedule(topics: list[str], total: int, rng: random.Random) -> list[str]:
    if not topics:
        raise ValueError("topics list is empty")
    pool = list(topics)
    scheduled: list[str] = []
    while len(scheduled) < total:
        rng.shuffle(pool)
        scheduled.extend(pool)
    return scheduled[:total]


def build_input_context_schedule(total: int, rng: random.Random) -> list[str]:
    required = ["user_files_required"] * (total // 2)
    public = ["public_only"] * (total - len(required))
    scheduled = required + public
    rng.shuffle(scheduled)
    return scheduled


def infer_input_material_hint(topic: str, bundle: dict[str, Any]) -> str:
    if any(keyword in topic for keyword in ["合同", "条款", "发票", "票据", "简历", "账单", "流水"]):
        return "基于我手头现有的合同、票据、截图、账单或原始材料来做，不要完全改写成纯公开信息查询。"
    if any(keyword in topic for keyword in ["申请", "办理", "核验", "认定", "证明", "报名"]):
        return "默认我手头已经有部分申报材料、截图、历史记录或原始文件，你要结合这些现有材料来判断缺口和下一步。"
    if any(keyword in topic for keyword in FILE_DEPENDENCY_TOPIC_KEYWORDS):
        return "任务要建立在我已有的文件、截图、原始材料或整理底稿之上，而不是只靠公开网页现查。"
    if bundle.get("template") in {"file_extract_plus_report_package", "extract_plus_delivery_refine", "document_plus_multiformat_output"}:
        return "任务明确依赖我手头已有文件、截图或现成材料，请把这一前提写进计划。"
    return "虽然主题也能查公开信息，但这条样本请默认我手头有一批材料、截图、历史记录或原始文件，需要基于这些内容做进一步判断和整理。"

def template_topic_eligible(template: dict[str, Any], topic: str) -> bool:
    template_name = str(template.get("name", "")).strip()
    if template_name in {"file_extract_plus_report_package", "extract_plus_delivery_refine", "document_plus_multiformat_output"}:
        return any(keyword in topic for keyword in EXTRACT_FRIENDLY_KEYWORDS)
    return True


def sample_bundle_with_fallbacks(
    sampler_module: Any,
    templates: list[dict[str, Any]],
    template_index: int,
    profiles: dict[str, dict[str, Any]],
    groups: dict[str, dict[str, list[str]]],
    usage_by_role: Any,
    recent_by_role: Any,
    rng: random.Random,
    topic: str,
) -> dict[str, Any]:
    preferred_templates = [tpl for i, tpl in enumerate(templates) if i == template_index and template_topic_eligible(tpl, topic)]
    eligible_templates = [tpl for i, tpl in enumerate(templates) if i != template_index and template_topic_eligible(tpl, topic)]
    fallback_templates = [tpl for tpl in templates if tpl not in preferred_templates and tpl not in eligible_templates]
    ordered_templates = preferred_templates + eligible_templates + fallback_templates
    last_exc: Exception | None = None
    for enforce_topic in (True, False):
        active_topic = topic if enforce_topic else None
        for template in ordered_templates:
            try:
                bundle = sampler_module.sample_bundle(
                    template,
                    profiles,
                    groups,
                    usage_by_role,
                    recent_by_role,
                    rng,
                    topic=active_topic,
                )
                if not enforce_topic:
                    bundle["sampling_relaxation"] = "topic_constraint_relaxed"
                return bundle
            except RuntimeError as exc:
                last_exc = exc
                continue
    assert last_exc is not None
    raise last_exc

def load_personas(path: Path) -> list[dict[str, Any]]:
    personas = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        profile = data.get("user_profile", data)
        if isinstance(profile, dict):
            personas.append(profile)
    return personas


def persona_summary(profile: dict[str, Any]) -> str:
    parts = []
    for key in ["职业", "常住地", "家庭情况", "性格"]:
        value = str(profile.get(key, "")).strip()
        if value:
            parts.append(value)
    return "，".join(parts[:4])


def load_sampler_module():
    import importlib.util

    path = EXP_ROOT / "step1_skeleton_sampler.py"
    spec = importlib.util.spec_from_file_location("gpt_exp_step1_sampler", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def skill_block(skills: list[str], profiles: dict[str, dict[str, Any]]) -> str:
    lines = []
    for slug in skills:
        profile = profiles[slug]
        description = " ".join(str(profile.get("description", "")).split())
        lines.append(
            f"- {slug} | desc={description} | roles={profile.get('intent_roles', [])} | "
            f"domain={profile.get('domain_tags', [])} | in={profile.get('artifact_in', [])} | out={profile.get('artifact_out', [])}"
        )
    return "\n".join(lines)


def chain_block(items: list[dict[str, Any]]) -> str:
    return "\n".join(f"- role={item['role']} | slug={item['slug']}" for item in items) or "- 无"




def artifact_phrase(profile: dict[str, Any]) -> str:
    artifact_out = profile.get("artifact_out", []) or ["text"]
    mapping = {
        "html": "可直接查看的网页报告",
        "docx": "Word文档",
        "xlsx": "电子表格",
        "pptx": "演示文稿",
        "audio": "语音音频",
        "mp3": "MP3音频",
        "chart": "图表结果",
        "image": "图片结果",
        "text": "文字结果",
        "pdf": "PDF文件",
        "web": "网页资料摘要",
    }
    return "、".join(mapping.get(item, item) for item in artifact_out[:2])


def infer_global_constraints(topic: str, persona: dict[str, Any], bundle: dict[str, Any]) -> list[str]:
    city = str(persona.get("常住地", "")).strip()
    persona_hint = persona_summary(persona)
    constraints: list[str] = []
    if city and any(keyword in topic for keyword in ["价格", "运费", "时效", "补贴", "资费", "落地价", "办理", "政策", "医院", "宽带"]):
        constraints.append(f"结果必须结合{city}当地的价格、规则、渠道或服务范围来判断，不能只给泛化结论。")
    if any(keyword in topic for keyword in ["对比", "参数", "选购", "资费", "报价", "套餐", "落地价", "型号"]):
        constraints.append("需要把决定性差异压缩成可直接拍板的取舍标准，不能只堆信息。")
    if any(keyword in topic for keyword in ["申请", "办理", "报销", "补贴", "材料", "核验", "报名", "评审"]):
        constraints.append("要把容易遗漏的材料、门槛、日期或规则变化点提前拎出来，减少执行时返工。")
    if persona_hint and any(keyword in persona_hint for keyword in ["对象", "家庭", "有娃", "独居", "父母", "同事"]):
        constraints.append("结果除了自己要看懂，还要便于转给相关的人一起判断或直接照着执行。")
    if bundle.get("secondary_chain_kind") or bundle.get("enhancement_chain_kind"):
        constraints.append("结果不能只有一份大而全主稿，还要拆出更利于拍板或更利于执行的适配结果。")
    constraints.append("最终结果不能只停留在整理信息，要形成带优先级或明确推荐方向的收束结果。")
    ordered: list[str] = []
    for item in constraints:
        if item not in ordered:
            ordered.append(item)
    return ordered[:3]


def infer_delivery_layers(bundle: dict[str, Any], profiles: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    layers: list[dict[str, str]] = []
    primary_chain = bundle.get("primary_chain", [])
    enhancement_chain = bundle.get("enhancement_chain", [])
    secondary_kind = str(bundle.get("secondary_chain_kind", "")).strip()
    enhancement_kind = str(bundle.get("enhancement_chain_kind", "")).strip()
    if primary_chain:
        deliver_profile = profiles[primary_chain[-1]["slug"]]
        layers.append({"layer": "main", "goal": f"主交付承担完整结果闭环，核心形式偏向{artifact_phrase(deliver_profile)}。"})
    if secondary_kind:
        mapping = {
            "refinement_for_decision": "补一层更利于拍板的决策版，把重点差异、优先级和建议收得更直接。",
            "presentation_support": "补一层更直观的阅读版，方便快速浏览和吸收关键信息。",
            "source_check_support": "补一层有限核查结果，把来源、规则门槛或关键字段的可靠性讲清楚。",
            "analysis_with_evidence_check": "补一层依据说明，把结论和关键证据之间的对应关系压实。",
            "publish_support": "补一层可直接转发的版本，方便给别人看或用于沟通。",
        }
        layers.append({"layer": "secondary", "goal": mapping.get(secondary_kind, "补一层围绕主任务的辅助结果。")})
    if enhancement_chain or enhancement_kind:
        mapping = {
            "presentation_support": "再补一层更好读、更适合快速扫读的辅助呈现。",
            "decision_support": "再补一层更短、更利于快速拍板或横向比较的结果。",
            "execution_support": "再补一层更便于照着执行的整理结果，例如顺序、清单或操作提示。",
            "audience_adaptation": "再补一层更适合转给家人、对象、同事或领导阅读的版本。",
        }
        layers.append({"layer": "enhancement", "goal": mapping.get(enhancement_kind, "再补一层围绕最终结果的适配版本。")})
    return layers[:3]


def delivery_layers_block(layers: list[dict[str, str]]) -> str:
    if not layers:
        return "- 无"
    return "\n".join(f"- {row['layer']}: {row['goal']}" for row in layers)





def chat_json_with_retries(
    client: OpenAICompatClient,
    system_prompt: str,
    user_prompt: str,
    *,
    retries: int,
) -> dict[str, Any]:
    return call_with_retries(
        lambda: client.chat_json(system_prompt, user_prompt),
        retries=retries,
        is_retryable=is_transient_llm_error,
    )


STEP1_SYSTEM_PROMPT = (
    "你是一个benchmark任务生成器。"
    "你会看到一个已经按角色均衡采样过的skill bundle。"
    "你的任务是写出扎实、完整、单目标的hidden_plan。"
    "不要提skill名字，只输出一个合法JSON对象。"
)


def build_prompt(sample_id: str, topic: str, persona: dict[str, Any], bundle: dict[str, Any], profiles: dict[str, dict[str, Any]], input_context: str, input_material_hint: str) -> str:
    primary_block = chain_block(bundle["primary_chain"])
    secondary_block = chain_block(list(bundle.get("secondary_chain", [])))
    enhancement_block = chain_block(list(bundle.get("enhancement_chain", [])))
    support_block = chain_block(list(bundle.get("support_slots", [])))
    all_skills = bundle["skills"]
    persona_text = persona_summary(persona)
    constraints = infer_global_constraints(topic, persona, bundle)
    delivery_layers = infer_delivery_layers(bundle, profiles)
    return f"""请基于给定的bundle，生成1条中文benchmark任务的hidden_plan，并输出JSON对象。

sample_id: {sample_id}
topic: {topic}
persona: {persona_text}
template: {bundle['template']}
template_desc: {bundle.get('description', '')}
secondary_chain_kind: {bundle.get('secondary_chain_kind', '')}
enhancement_chain_kind: {bundle.get('enhancement_chain_kind', '')}
input_context: {input_context}

primary chain:
{primary_block}

secondary chain:
{secondary_block}

enhancement chain:
{enhancement_block}

support slots:
{support_block}

global constraints:
{chr(10).join(f"- {item}" for item in constraints) if constraints else "- 无"}

delivery layers:
{delivery_layers_block(delivery_layers)}

bundle skills profile:
{skill_block(all_skills, profiles)}

input material hint:
- {input_material_hint}

要求：
- 整条任务必须围绕单一topic展开，不能拆成两个互不相关的小任务
    - hidden_plan 必须体现主链、副链、增强链共同服务同一个最终目标，不能写成多个独立小任务
    - primary chain 负责主任务闭环
    - secondary chain 优先承担“决策版 / 依据版 / 转发版 / 核查版”中的一种明确用途，不要默认写成泛泛的“一致性复核”
    - enhancement chain 优先承担“执行版 / 受众适配版 / 快速拍板版 / 快速浏览版”中的一种明确用途
    - support slots 只作为补强，不要喧宾夺主
- 不要提 skill slug 或 skill 名字
- 难度来自任务结构和交付要求，不是堆术语
- 优先让任务听起来像真实用户确实会提的复杂请求
- hidden_plan 里要体现 2 到 3 层交付物各自承担的用途，优先形成“主结果 + 决策适配层 + 执行/转发适配层”
- hidden_plan 里要吸收 2 到 3 条现实约束，例如地点、时间、试错成本、阅读对象、执行代价
- hidden_plan 不能把所有中间动作都说死，要留出一部分隐含推理工作给执行智能体自己完成
- hidden_plan 至少要出现一次“基于主结果继续收束成更适合拍板/执行/转发的版本”的结构
- 如果 input_context = user_files_required，hidden_plan 必须明确建立在“用户手头已有文件、截图、原始材料、底稿或历史记录”之上，不能改写成纯公开信息检索任务
- 如果 input_context = user_files_required，至少要有 1 到 2 步明确提到基于现有材料做提取、核对、归并、补缺或判断

输出JSON对象，字段只有：
- topic
- persona_hint
- hidden_plan

约束：
- hidden_plan 必须是 6 到 8 个完整中文步骤组成的 JSON 数组
- persona_hint 用一句中文短摘要
"""








def normalize_record(
    sample_id: str,
    raw: dict[str, Any],
    topic: str,
    persona: dict[str, Any],
    bundle: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
    input_context: str,
    input_material_hint: str,
) -> dict[str, Any]:
    hidden_raw = raw.get("hidden_plan", [])
    if isinstance(hidden_raw, str):
        parts = re.split(r"[\n；;。]", hidden_raw)
        hidden_plan = [p.strip(" -1234567890.") for p in parts if p.strip(" -1234567890.")]
    else:
        hidden_plan = [str(x).strip() for x in hidden_raw if str(x).strip()]
    hidden_plan = [step for step in hidden_plan if len(step) >= 4][:8]
    if len(hidden_plan) < 6:
        raise ValueError("hidden_plan shorter than 6 steps")

    persona_hint = str(raw.get("persona_hint", "")).strip().replace("；", "，") or persona_summary(persona)
    primary_chain = list(bundle["primary_chain"])
    secondary_chain = list(bundle.get("secondary_chain", []))
    enhancement_chain = list(bundle.get("enhancement_chain", []))
    support_slots = list(bundle.get("support_slots", []))
    global_constraints = infer_global_constraints(topic, persona, bundle)
    delivery_layers = infer_delivery_layers(bundle, profiles)
    chain_skills = []
    for item in primary_chain:
        chain_skills.append(
            {
                "slug": item["slug"],
                "selected_role": item["role"],
                "slot_type": "required",
                "chain_name": "primary_chain",
                "selection_source": "template_required",
            }
        )
    for item in secondary_chain:
        chain_skills.append(
            {
                "slug": item["slug"],
                "selected_role": item["role"],
                "slot_type": "required",
                "chain_name": "secondary_chain",
                "selection_source": "template_required_secondary",
            }
        )
    for item in enhancement_chain:
        chain_skills.append(
            {
                "slug": item["slug"],
                "selected_role": item["role"],
                "slot_type": "required",
                "chain_name": "enhancement_chain",
                "selection_source": "template_required_enhancement",
            }
        )
    for item in support_slots:
        chain_skills.append(
            {
                "slug": item["slug"],
                "selected_role": item["role"],
                "slot_type": "support",
                "chain_name": "support_chain",
                "selection_source": "template_support_or_backfill",
            }
        )
    return {
        "id": sample_id,
        "topic": str(raw.get("topic", "")).strip() or topic,
        "persona_hint": persona_hint,
        "input_context": input_context,
        "input_material_hint": input_material_hint,
        "hidden_plan": hidden_plan,
        "chain_design": {
            "sampling_mode": "single_topic_dual_chain_plus_enhancement",
            "template": bundle["template"],
            "template_description": bundle.get("description", ""),
            "secondary_chain_kind": bundle.get("secondary_chain_kind", ""),
            "enhancement_chain_kind": bundle.get("enhancement_chain_kind", ""),
            "primary_chain": primary_chain,
            "secondary_chain": secondary_chain,
            "enhancement_chain": enhancement_chain,
            "support_slots": support_slots,
        },
        "global_constraints": global_constraints,
        "delivery_layers": delivery_layers,
        "chain_skills": chain_skills,
    }


def generate_one_record(
    sample_id: str,
    topic: str,
    persona: dict[str, Any],
    bundle: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
    input_context: str,
    input_material_hint: str,
    client: OpenAICompatClient,
    retries: int,
) -> dict[str, Any]:
    prompt = build_prompt(sample_id, topic, persona, bundle, profiles, input_context, input_material_hint)
    raw = chat_json_with_retries(
        client,
        STEP1_SYSTEM_PROMPT,
        prompt,
        retries=retries,
    )
    return normalize_record(
        sample_id,
        raw,
        topic,
        persona,
        bundle,
        profiles,
        input_context,
        input_material_hint,
    )

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate experimental step1 hidden-plan JSONL from bundle shards.")
    parser.add_argument("total", type=int, nargs="?", default=12)
    parser.add_argument("out_path", nargs="?", default=None)
    parser.add_argument("--artifacts-root", type=Path, default=ARTIFACTS_ROOT)
    parser.add_argument("--topics-path", type=Path, default=TOPICS_PATH)
    parser.add_argument("--personas-path", type=Path, default=PERSONAS_PATH)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--retries", type=int, default=2)
    add_openai_client_args(parser, include_timeout=True)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    OUTPUTS_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out_path) if args.out_path else OUTPUTS_ROOT / f"step1_hidden_plans_{args.total}.jsonl"
    sampler = load_sampler_module()
    profiles = sampler.load_profiles(args.artifacts_root)
    topics = load_topics(args.topics_path)
    personas = load_personas(args.personas_path)
    require_api_key(args.api_key)
    sampler_rng = random.Random(args.seed)
    content_rng = random.Random(args.seed + 1009)
    usage_by_role = sampler.defaultdict(sampler.Counter)
    recent_by_role = sampler.defaultdict(lambda: sampler.deque(maxlen=6))
    groups = sampler.load_groups(args.artifacts_root)
    templates = load_json(args.artifacts_root / "task_templates.json").get("templates", [])

    client = build_openai_client_from_args(args, max_retries=max(1, args.retries + 1))

    topic_schedule = build_topic_schedule(topics, args.total, content_rng)
    input_context_schedule = build_input_context_schedule(args.total, content_rng)

    records: list[dict[str, Any]] = []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("", encoding="utf-8")
    write_lock = Lock()

    def process_one(idx: int) -> dict[str, Any]:
        sample_id = f"sample_{idx + 1:03d}"
        template_index = idx % len(templates)
        topic = topic_schedule[idx]
        persona = content_rng.choice(personas)
        input_context = input_context_schedule[idx]
        input_material_hint = infer_input_material_hint(topic, {"template": templates[template_index].get("name", "")})
        bundle = sample_bundle_with_fallbacks(
            sampler, templates, template_index, profiles, groups,
            usage_by_role, recent_by_role, sampler_rng, topic,
        )
        if input_context == "user_files_required":
            input_material_hint = infer_input_material_hint(topic, bundle)
        else:
            input_material_hint = ""
        record = generate_one_record(
            sample_id,
            topic,
            persona,
            bundle,
            profiles,
            input_context,
            input_material_hint,
            client,
            args.retries,
        )
        append_jsonl(out_path, record, write_lock)
        print(f"[ok] {sample_id}")
        return record

    for idx in range(args.total):
        record = process_one(idx)
        records.append(record)

    print(json.dumps({"out_path": str(out_path), "records": len(records)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
