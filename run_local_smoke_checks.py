#!/usr/bin/env python3
"""
Run local compile and smoke checks without calling remote LLM APIs.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PYTHON_FILES = [
    "pipeline_common.py",
    "step0_incremental_index.py",
    "step1_skeleton_sampler.py",
    "step1_generate_hidden_plans.py",
    "step2_rewrite_richer.py",
    "step3_naturalize_diversify.py",
    "step4_build_workspaces.py",
]


class DummyClient:
    def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {
            "topic": "家庭收支核算表",
            "persona_hint": "测试 persona",
            "hidden_plan": [
                "先整理我手头已有的账单、流水和截图材料，统一字段口径。",
                "从现有材料里提取核心收支明细，补齐缺失记录并标注异常项。",
                "按固定周期和支出类别重组数据，识别真正拉高压力的超支项。",
                "输出一份可持续维护的主核算表，作为后续判断和调整的唯一底稿。",
                "基于主表再压一版更利于拍板的决策建议，明确哪些开支该先收紧。",
                "补一版便于直接执行的提醒清单，避免后续继续重复踩坑。",
            ],
        }

    def chat_text(self, system_prompt: str, user_prompt: str) -> str:
        if "step3" in system_prompt.lower():
            return "我手上有这半年账单和流水，想让你先整理成收支主表，再顺手压一版能让我直接拍板的简明建议，重点把超支项和该收紧的地方讲明白。"
        return "请基于我现有的账单、流水和截图，先整理出一份家庭收支主表，再压一版能直接拍板的决策建议，把超支项、可收紧项和执行提醒讲清楚。"


def run_compile_check() -> None:
    cmd = [sys.executable, "-m", "py_compile", *PYTHON_FILES]
    subprocess.run(cmd, cwd=ROOT, check=True)


def run_sampler_smoke() -> dict:
    raw = subprocess.check_output([sys.executable, "step1_skeleton_sampler.py", "--count", "1"], cwd=ROOT, text=True)
    payload = json.loads(raw)
    return {
        "bundle_count": len(payload.get("bundles", [])),
        "primary_chain": payload["bundles"][0]["primary_chain"],
    }


def run_pipeline_smoke() -> dict:
    import step1_generate_hidden_plans as step1
    import step2_rewrite_richer as step2
    import step3_naturalize_diversify as step3

    sampler = step1.load_sampler_module()
    profiles = sampler.load_profiles(ROOT / "artifacts")
    groups = sampler.load_groups(ROOT / "artifacts")
    templates = step1.load_json(ROOT / "artifacts" / "task_templates.json").get("templates", [])
    usage_by_role = sampler.defaultdict(sampler.Counter)
    recent_by_role = sampler.defaultdict(lambda: sampler.deque(maxlen=6))
    rng = random.Random(17)
    client = DummyClient()

    bundle = step1.sample_bundle_with_fallbacks(
        sampler, templates, 0, profiles, groups,
        usage_by_role, recent_by_role, rng, "家庭收支核算表",
    )
    step1_record = step1.generate_one_record(
        "sample_001",
        "家庭收支核算表",
        {"职业": "测试", "常住地": "上海"},
        bundle,
        profiles,
        "user_files_required",
        "任务明确依赖我手头已有文件。",
        client,
        0,
    )
    step2_record = step2.rewrite_record(step1_record, 0, client)
    step3_record = step3.rewrite_record(step2_record, 0, client)
    return {
        "step1_keys": sorted(step1_record.keys()),
        "step2_query_length": len(str(step2_record.get("query", ""))),
        "step3_query_length": len(str(step3_record.get("query", ""))),
        "step3_has_query_step2": "query_step2" in step3_record,
    }


def main() -> int:
    run_compile_check()
    sampler_summary = run_sampler_smoke()
    pipeline_summary = run_pipeline_smoke()
    print(
        json.dumps(
            {
                "compile": "ok",
                "sampler_smoke": sampler_summary,
                "pipeline_smoke": pipeline_summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
