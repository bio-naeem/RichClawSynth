#!/usr/bin/env python3
"""
Experimental incremental step0 builder.

This script is intentionally isolated under gpt-exp/ so the existing pipeline
and references remain untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Any

from pipeline_common import (
    OpenAICompatClient,
    add_openai_client_args,
    build_openai_client_from_args,
    call_with_retries,
    is_transient_llm_error,
    load_json,
    load_project_dotenv,
    require_api_key,
    write_json,
    write_jsonl,
)


load_project_dotenv()


EXP_ROOT = Path(__file__).resolve().parent
CONFIG_ROOT = EXP_ROOT / "config"
DEFAULT_SKILLS_ROOT = Path(os.environ.get("SKILLS_POOL", str(EXP_ROOT / "skills-selected")))
DEFAULT_OUT_ROOT = EXP_ROOT / "artifacts"
DEFAULT_OVERRIDES_PATH = EXP_ROOT / "references" / "manual_overrides.json"
TASK_TEMPLATES_CONFIG_PATH = CONFIG_ROOT / "task_templates.json"



def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def parse_frontmatter(skill_dir: Path) -> dict[str, str] | None:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None
    content = skill_file.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_skills(skills_root: Path) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        frontmatter = parse_frontmatter(skill_dir)
        if not frontmatter:
            continue
        skill_file = skill_dir / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")
        skills.append(
            {
                "slug": skill_dir.name,
                "name": frontmatter.get("name", skill_dir.name),
                "description": frontmatter.get("description", ""),
                "skill_path": str(skill_dir),
                "skill_md_path": str(skill_file),
                "content_hash": sha1_text(content),
                "excerpt": "\n".join(content.splitlines()[:40]),
            }
        )
    return skills


def normalize_short_list(values: Any, fallback: list[str], limit: int) -> list[str]:
    source = values if isinstance(values, list) else fallback
    cleaned: list[str] = []
    seen = set()
    for value in source:
        text = str(value).strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned[:limit] or fallback[:]


def is_meta_orchestration_skill(skill: dict[str, Any], profile: dict[str, Any]) -> bool:
    """Check whether a skill is a meta-orchestration skill.

    Relies on the ``is_meta`` boolean field that the LLM produces during
    profile generation.  Falls back to ``False`` for legacy profiles that
    lack the field.
    """
    return bool(profile.get("is_meta", False))


def normalize_profile(skill: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(profile)
    normalized["slug"] = skill["slug"]
    normalized["name"] = skill["name"]
    normalized["description"] = skill["description"]
    normalized["intent_roles"] = normalize_short_list(normalized.get("intent_roles"), ["transform"], 3)
    normalized["artifact_in"] = normalize_short_list(normalized.get("artifact_in"), ["text"], 3)
    normalized["artifact_out"] = normalize_short_list(normalized.get("artifact_out"), ["text"], 3)
    normalized["domain_tags"] = normalize_short_list(normalized.get("domain_tags"), ["general"], 3)
    allowed_roles = normalize_short_list(normalized.get("allowed_roles"), normalized["intent_roles"], 4)
    normalized["allowed_roles"] = [role for role in allowed_roles if role in normalized["intent_roles"]] or list(normalized["intent_roles"])
    normalized.setdefault("task_eligible", True)
    normalized.setdefault("allow_required_slots", True)
    normalized.setdefault("allow_primary_chain", True)

    if is_meta_orchestration_skill(skill, normalized):
        keep_roles = [role for role in normalized["allowed_roles"] if role in {"review", "transform", "enhance", "publish"}]
        if not keep_roles:
            if "review" in normalized["intent_roles"]:
                keep_roles = ["review"]
            elif "transform" in normalized["intent_roles"]:
                keep_roles = ["transform"]
            else:
                keep_roles = [normalized["intent_roles"][0]]
        normalized["allowed_roles"] = keep_roles
        normalized["allow_primary_chain"] = False
        normalized["normalization_note"] = "soft_demote_meta_orchestration"

    return normalized


def llm_profile(client: OpenAICompatClient, skill: dict[str, Any]) -> dict[str, Any]:
    system_prompt = (
        "You are designing an incremental skill index for downstream task sampling. "
        "Return one JSON object only."
    )
    user_prompt = f"""
Generate a compact profile for one skill. Keep labels short and normalized.

Skill:
- slug: {skill["slug"]}
- name: {skill["name"]}
- description: {skill["description"]}
- excerpt:
{skill["excerpt"]}

Return JSON with exactly these fields:
- slug
- intent_roles: array of 1-3 labels from collect/extract/transform/analyze/deliver/enhance/publish/review
- artifact_in: array of short labels
- artifact_out: array of short labels
- domain_tags: array of short labels
- is_meta: boolean, true ONLY if this skill is a meta-orchestration / agent-autonomy / workflow-management / system-framework skill (i.e. it controls the agent lifecycle, orchestrates other tools, or manages sessions/planning rather than producing direct business outputs). false for all normal functional skills.
- rationale: short string
"""
    data = client.chat_json(system_prompt, user_prompt)
    data["slug"] = skill["slug"]
    data["name"] = skill["name"]
    data["description"] = skill["description"]
    data["source"] = "llm"
    return data


def group_relation(anchor: dict[str, Any], other: dict[str, Any]) -> tuple[str, str] | None:
    if anchor["slug"] == other["slug"]:
        return None

    out_set = set(anchor.get("artifact_out", []))
    role_a = set(anchor.get("intent_roles", []))
    role_b = set(other.get("intent_roles", []))
    domains_a = set(anchor.get("domain_tags", []))
    domains_b = set(other.get("domain_tags", []))
    domain_overlap = domains_a & domains_b

    primary_a = (anchor.get("intent_roles") or ["transform"])[0]
    primary_b = (other.get("intent_roles") or ["transform"])[0]
    if primary_a == primary_b and domain_overlap and (out_set & set(other.get("artifact_out", []))):
        common = sorted(domain_overlap)[0]
        return ("substitute", f"same primary role and overlapping outputs in {common}")
    if role_a & {"publish"} and role_b & {"publish"} and not domain_overlap:
        return ("anti_pattern", "two publish-oriented skills from different domains can make the task feel split")
    return None


def build_groups(anchor: dict[str, Any], profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    groups = {"substitute": [], "anti_pattern": []}
    for other_slug, other in profiles.items():
        scored = group_relation(anchor, other)
        if not scored:
            continue
        relation_type, _rationale = scored
        groups[relation_type].append(other_slug)
    groups["substitute"] = sorted(set(groups["substitute"]))
    groups["anti_pattern"] = sorted(set(groups["anti_pattern"]))
    return {
        "anchor": anchor["slug"],
        "groups": groups,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an incremental experimental skill index.")
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS_ROOT)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES_PATH)
    parser.add_argument("--refresh-skill", action="append", default=[], help="refresh one or more slugs")
    parser.add_argument("--all", action="store_true", help="refresh all skills")
    parser.add_argument("--workers", type=int, default=10, help="concurrent workers for LLM calls")
    add_openai_client_args(parser, include_timeout=True)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    skills = load_skills(args.skills_root)
    overrides = load_overrides(args.overrides)
    skill_map = {skill["slug"]: skill for skill in skills}
    if args.all:
        target_slugs = sorted(skill_map)
    elif args.refresh_skill:
        missing = [slug for slug in args.refresh_skill if slug not in skill_map]
        if missing:
            raise SystemExit(f"Unknown slugs: {', '.join(missing)}")
        target_slugs = sorted(set(args.refresh_skill))
    else:
        raise SystemExit("Pass --all or at least one --refresh-skill")

    profiles_dir = args.out_root / "profiles"
    groups_dir = args.out_root / "groups"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    groups_dir.mkdir(parents=True, exist_ok=True)

    require_api_key(args.api_key)
    client = build_openai_client_from_args(args, max_retries=2)

    # Load cached profiles for skills not being refreshed
    profiles: dict[str, dict[str, Any]] = {}
    skills_to_refresh = []
    for skill in skills:
        profile_path = profiles_dir / f"{skill['slug']}.json"
        if profile_path.exists() and skill["slug"] not in target_slugs:
            profiles[skill["slug"]] = json.loads(profile_path.read_text(encoding="utf-8"))
        else:
            skills_to_refresh.append(skill)

    def process_skill(skill: dict[str, Any]) -> dict[str, Any]:
        profile = call_with_retries(
            lambda: llm_profile(client, skill),
            retries=2,
            is_retryable=is_transient_llm_error,
        )
        profile = normalize_profile(skill, profile)
        override = overrides.get(skill["slug"])
        if override:
            profile.update(override)
            profile["source"] = f"{profile.get('source', 'llm')}+override"
        profile = normalize_profile(skill, profile)
        profile["content_hash"] = skill["content_hash"]
        profile["updated_at"] = int(time.time())
        write_json(profiles_dir / f"{skill['slug']}.json", profile)
        print(f"[ok] {skill['slug']}", file=sys.stderr)
        return profile

    write_lock = Lock()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_skill, skill): skill for skill in skills_to_refresh}
        for future in as_completed(futures):
            profile = future.result()
            with write_lock:
                profiles[profile["slug"]] = profile

    impacted = sorted(set(target_slugs))
    for slug in target_slugs:
        for other_slug in profiles:
            if other_slug != slug:
                impacted.append(other_slug)
    impacted = sorted(set(impacted))

    for slug in impacted:
        anchor = profiles[slug]
        group_bundle = build_groups(anchor, profiles)
        write_json(groups_dir / f"{slug}.json", {"anchor": slug, "groups": group_bundle["groups"]})

    manifest = {
        "skills_root": str(args.skills_root),
        "out_root": str(args.out_root),
        "model": args.model,
        "api_base": args.api_base,
        "overrides_path": str(args.overrides),
        "override_count": len(overrides),
        "skill_count": len(skills),
        "updated_slugs": target_slugs,
        "updated_at": int(time.time()),
    }
    write_json(args.out_root / "manifest.json", manifest)
    write_json(args.out_root / "task_templates.json", load_json(TASK_TEMPLATES_CONFIG_PATH))
    write_jsonl(args.out_root / "profiles.jsonl", [profiles[slug] for slug in sorted(profiles)])
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
