#!/usr/bin/env python3
"""
Build lightweight workspaces from gpt-exp step2/step3 JSONL outputs.

This mirrors the original repo's workspace materialization target, but reads
the experimental schema based on chain_design / chain_skills.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline_common import load_jsonl, load_project_dotenv


load_project_dotenv()

EXP_ROOT = Path(__file__).resolve().parent
DEFAULT_SKILLS_POOL = Path(os.environ.get("SKILLS_POOL", str(EXP_ROOT / "skills-selected")))
DEFAULT_OUTPUT_ROOT = EXP_ROOT / "workspace_outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build lightweight workspaces from gpt-exp JSONL outputs.")
    parser.add_argument("input_jsonl", help="input JSONL from gpt-exp step2 or step3")
    parser.add_argument("--tag", required=True, help="bundle tag, used in output directory naming")
    parser.add_argument("--workspace-root", default=str(DEFAULT_OUTPUT_ROOT), help="base directory for the workspace bundle")
    parser.add_argument(
        "--workspace-prefix",
        default="workspace",
        help="workspace directory prefix, final names look like <prefix>_<index:03d>",
    )
    parser.add_argument("--count", type=int, default=None, help="number of workspaces to build (default: all)")
    parser.add_argument(
        "--skills-source",
        choices=["all", "required-only", "primary-only", "support-only"],
        default="all",
        help="which skill subset to symlink into each workspace",
    )
    parser.add_argument("--skills-pool", default=str(DEFAULT_SKILLS_POOL), help="skills pool root")
    parser.add_argument("--force", action="store_true", help="overwrite an existing bundle directory")
    parser.add_argument("--dry-run", action="store_true", help="print actions without writing files")
    return parser.parse_args()

def bundle_dir(workspace_root: Path, tag: str) -> Path:
    return workspace_root / tag / f"{tag}-work"


def workspace_name(index: int, prefix: str) -> str:
    clean = str(prefix).strip().strip("_") or "workspace"
    return f"{clean}_{index:03d}"


def unique_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for item in items:
        slug = str(item).strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        ordered.append(slug)
    return ordered


def chain_slugs(chain_items: list[dict[str, Any]]) -> list[str]:
    return unique_preserve_order([str(item.get("slug", "")).strip() for item in chain_items])


def supporting_skills(record: dict[str, Any]) -> list[str]:
    chain_skills = record.get("chain_skills", [])
    if isinstance(chain_skills, list) and chain_skills:
        return unique_preserve_order([str(item.get("slug", "")).strip() for item in chain_skills])

    chain_design = record.get("chain_design", {}) if isinstance(record.get("chain_design"), dict) else {}
    merged = (
        chain_slugs(list(chain_design.get("primary_chain", []) or []))
        + chain_slugs(list(chain_design.get("secondary_chain", []) or []))
        + chain_slugs(list(chain_design.get("enhancement_chain", []) or []))
        + chain_slugs(list(chain_design.get("support_slots", []) or []))
    )
    return unique_preserve_order(merged)


def core_path(record: dict[str, Any]) -> list[str]:
    chain_design = record.get("chain_design", {}) if isinstance(record.get("chain_design"), dict) else {}
    return chain_slugs(list(chain_design.get("primary_chain", []) or []))


def aux_skills(record: dict[str, Any]) -> list[str]:
    chain_design = record.get("chain_design", {}) if isinstance(record.get("chain_design"), dict) else {}
    merged = (
        chain_slugs(list(chain_design.get("secondary_chain", []) or []))
        + chain_slugs(list(chain_design.get("enhancement_chain", []) or []))
        + chain_slugs(list(chain_design.get("support_slots", []) or []))
    )
    return unique_preserve_order(merged)


def required_only_skills(record: dict[str, Any]) -> list[str]:
    chain_skills = record.get("chain_skills", [])
    if isinstance(chain_skills, list) and chain_skills:
        return unique_preserve_order(
            [
                str(item.get("slug", "")).strip()
                for item in chain_skills
                if str(item.get("slot_type", "")).strip() == "required"
            ]
        )
    return unique_preserve_order(core_path(record) + aux_skills(record))


def support_only_skills(record: dict[str, Any]) -> list[str]:
    chain_design = record.get("chain_design", {}) if isinstance(record.get("chain_design"), dict) else {}
    return chain_slugs(list(chain_design.get("support_slots", []) or []))


def record_skills(record: dict[str, Any], skills_source: str) -> list[str]:
    if skills_source == "primary-only":
        return core_path(record)
    if skills_source == "required-only":
        return required_only_skills(record)
    if skills_source == "support-only":
        return support_only_skills(record)
    return supporting_skills(record)


def workspace_record(record: dict[str, Any], workspace_dir: Path) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "result": record.get("query"),
        "scenario": record.get("scenario"),
        "topic": record.get("topic"),
        "persona_hint": record.get("persona_hint"),
        "supporting_skills": supporting_skills(record),
        "core_path": core_path(record),
        "aux_skills": aux_skills(record),
        "distractor_skills": [],
        "hidden_plan": list(record.get("hidden_plan", []) or []),
        "bundle_judge": record.get("bundle_judge"),
        "bundle_sampling": record.get("bundle_sampling"),
        "chain_design": record.get("chain_design"),
        "chain_skills": list(record.get("chain_skills", []) or []),
        "global_constraints": list(record.get("global_constraints", []) or []),
        "delivery_layers": list(record.get("delivery_layers", []) or []),
        "workspace_name": workspace_dir.name,
        "workspace_path": str(workspace_dir),
    }


def choose_balanced_records(records: list[dict[str, Any]], count: int, skills_source: str) -> list[dict[str, Any]]:
    if count >= len(records):
        return records[:]

    usage: Counter[str] = Counter()
    remaining = list(records)
    chosen = []

    while remaining and len(chosen) < count:
        best_idx = 0
        best_score = None
        for idx, record in enumerate(remaining):
            skills = record_skills(record, skills_source)
            if not skills:
                score = (float("inf"), float("inf"), float("inf"), idx)
            else:
                projected = [usage.get(slug, 0) + 1 for slug in skills]
                score = (
                    max(projected),
                    sum(projected) / len(projected),
                    -sum(1.0 / (usage.get(slug, 0) + 1) for slug in skills),
                    idx,
                )
            if best_score is None or score < best_score:
                best_score = score
                best_idx = idx
        picked = remaining.pop(best_idx)
        chosen.append(picked)
        for slug in record_skills(picked, skills_source):
            usage[slug] += 1
    return chosen


def ensure_skill_targets(records: list[dict[str, Any]], skills_source: str, skills_pool: Path) -> None:
    missing = set()
    for record in records:
        for slug in record_skills(record, skills_source):
            if not (skills_pool / slug).exists():
                missing.add(slug)
    if missing:
        raise RuntimeError(f"missing skills in skills_pool: {sorted(missing)}")


def prepare_bundle_directory(target: Path, force: bool, dry_run: bool) -> None:
    if target.exists():
        if not force:
            raise RuntimeError(f"bundle directory already exists: {target} (use --force to overwrite)")
        if dry_run:
            print(f"[dry-run] remove existing bundle: {target}")
        else:
            shutil.rmtree(target)
    if dry_run:
        print(f"[dry-run] ensure parent dir: {target.parent}")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)


def write_workspace(
    record: dict[str, Any],
    index: int,
    target_bundle: Path,
    workspace_prefix: str,
    skills_source: str,
    skills_pool: Path,
    dry_run: bool,
) -> None:
    ws_dir = target_bundle / workspace_name(index, workspace_prefix)
    skills_dir = ws_dir / "skills"
    payload = workspace_record(record, ws_dir)
    skill_slugs = record_skills(record, skills_source)

    if dry_run:
        print(f"[dry-run] create workspace: {ws_dir}")
        print(f"[dry-run] write record: {ws_dir / 'queries_persona.jsonl'}")
        for slug in skill_slugs:
            print(f"[dry-run] symlink {skills_dir / slug} -> {skills_pool / slug}")
        return

    skills_dir.mkdir(parents=True, exist_ok=True)
    with open(ws_dir / "queries_persona.jsonl", "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    for slug in skill_slugs:
        target = skills_pool / slug
        link_path = skills_dir / slug
        os.symlink(target, link_path)


def print_balance_summary(records: list[dict[str, Any]], skills_source: str) -> None:
    usage: Counter[str] = Counter()
    for record in records:
        for slug in record_skills(record, skills_source):
            usage[slug] += 1
    if not usage:
        print("[balance-summary] no skills linked", file=sys.stderr)
        return
    counts = sorted(usage.values())
    top = ", ".join(f"{slug}:{count}" for slug, count in usage.most_common(10))
    print(
        "[balance-summary] skills={} min={} median={} max={}".format(
            len(counts),
            counts[0],
            counts[len(counts) // 2],
            counts[-1],
        ),
        file=sys.stderr,
    )
    print(f"[balance-top] {top}", file=sys.stderr)


def main() -> int:
    opts = parse_args()
    input_path = Path(opts.input_jsonl)
    workspace_root = Path(opts.workspace_root)
    skills_pool = Path(opts.skills_pool)
    records = load_jsonl(input_path)
    if not records:
        raise RuntimeError(f"no records found in {input_path}")

    requested_count = opts.count if opts.count is not None else len(records)
    if requested_count <= 0:
        raise RuntimeError("--count must be positive")
    if requested_count > len(records):
        raise RuntimeError(f"requested {requested_count} workspaces but only {len(records)} records available")

    selected = choose_balanced_records(records, requested_count, opts.skills_source)
    ensure_skill_targets(selected, opts.skills_source, skills_pool)

    target_bundle = bundle_dir(workspace_root, opts.tag)
    prepare_bundle_directory(target_bundle, opts.force, opts.dry_run)

    if opts.dry_run:
        print(f"[dry-run] ensure bundle dir: {target_bundle}")
    else:
        target_bundle.mkdir(parents=True, exist_ok=True)

    for index, record in enumerate(selected, start=1):
        write_workspace(record, index, target_bundle, opts.workspace_prefix, opts.skills_source, skills_pool, opts.dry_run)
        print(f"[ok] {workspace_name(index, opts.workspace_prefix)}")

    print_balance_summary(selected, opts.skills_source)
    print(f"wrote {len(selected)} workspaces to {target_bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
