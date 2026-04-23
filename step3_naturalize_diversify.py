#!/usr/bin/env python3
"""
Experimental step3 that only naturalizes and diversifies step2 queries.
"""

from __future__ import annotations

import argparse
import json
import re
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

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

from prompts_step3_exp import STEP3_EXP_SYSTEM_PROMPT, STEP3_EXP_USER_PROMPT_TEMPLATE


load_project_dotenv()


STYLE_VARIANTS = [
    "写得像用户直接把事情抛出来，语气利落一点，但别太像命令。",
    "写得像用户先交代自己为什么卡住，再顺手补限制，语气自然一点。",
    "写得像用户已经自己看过一些东西，但越看越拿不准，所以希望 AI 直接收束成结论。",
    "写得像用户边说任务边带出结果怎么用，生活化一点，少一点“工作流说明”的感觉。",
    "写得像用户在聊天里补充要求，句子长短错开一点，不要每句结构都一样。",
    "写得像用户已经有点着急，想尽快拍板，但又不想因为信息不准吃亏。",
]


class NaturalizedQueryValidationError(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Experimental step3 naturalize/diversify pass under gpt-exp.")
    parser.add_argument("input_jsonl", help="input step2 JSONL")
    parser.add_argument("output_jsonl", help="output step3 JSONL")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=2)
    add_openai_client_args(parser, include_timeout=True)
    return parser.parse_args()


def style_instruction(sample_id: str) -> str:
    digits = "".join(ch for ch in sample_id if ch.isdigit())
    idx = int(digits or "0") % len(STYLE_VARIANTS)
    return STYLE_VARIANTS[idx]


def build_simple_block(values: list[str]) -> str:
    if not values:
        return "- 无"
    return "\n".join(f"- {value}" for value in values)


def build_prompt(rec: dict) -> str:
    chain_design = rec.get("chain_design", {}) if isinstance(rec.get("chain_design"), dict) else {}
    current_query = str(rec.get("query", "")).strip() or "未提供"
    return STEP3_EXP_USER_PROMPT_TEMPLATE.format(
        style_instruction=style_instruction(str(rec.get("id", ""))),
        persona_hint=str(rec.get("persona_hint", "")).strip() or "无",
        topic=str(rec.get("topic", "")).strip() or "未提供",
        input_context=str(rec.get("input_context", "")).strip() or "public_only",
        must_keep_input_material_hint=build_simple_block([str(rec.get("input_material_hint", "")).strip()] if str(rec.get("input_material_hint", "")).strip() else []),
        secondary_chain_kind=str(chain_design.get("secondary_chain_kind", "")).strip() or "未提供",
        must_keep_relative_paths=build_simple_block(list(rec.get("must_keep_relative_paths", []) or [])),
        must_keep_locations=build_simple_block(list(rec.get("must_keep_locations", []) or [])),
        must_keep_review_points=build_simple_block(list(rec.get("must_keep_review_points", []) or [])),
        current_query=current_query,
    )


def rewrite_record(rec: dict, retries: int, client: OpenAICompatClient) -> dict:
    return call_with_retries(
        lambda: _rewrite_record_once(rec, client),
        retries=retries,
        is_retryable=lambda exc: is_transient_llm_error(exc, extra_retryable=(NaturalizedQueryValidationError,)),
    )


def _rewrite_record_once(rec: dict, client: OpenAICompatClient) -> dict:
    original_query = str(rec.get("query", "")).strip()
    new_query = client.chat_text(
        STEP3_EXP_SYSTEM_PROMPT,
        build_prompt(rec),
    ).strip()
    new_query = re.sub(r"\s+", " ", new_query).strip()
    if len(new_query) < 24:
        raise NaturalizedQueryValidationError("step3 query too short")
    out = dict(rec)
    out["query_step2"] = original_query
    out["query"] = new_query
    return out


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
            print(f"[ok] {rec.get('id', 'unknown')}")
    print(json.dumps({"output_path": str(output_path), "count": len(rewritten_records)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
