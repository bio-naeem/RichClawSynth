#!/usr/bin/env python3
"""
Experimental step1 sampler built on top of the incremental step0 index.

This script samples skills by task skeleton instead of walking one directed graph.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from pipeline_common import load_json, load_project_dotenv


load_project_dotenv()

EXP_ROOT = Path(__file__).resolve().parent
ARTIFACTS_ROOT = EXP_ROOT / "artifacts"
CONFIG_ROOT = EXP_ROOT / "config"
TOPIC_TAXONOMY = load_json(CONFIG_ROOT / "topic_taxonomy.json")
PRIMARY_ROLE_OUTPUT_HINTS = {
    "collect": {"web", "text"},
    "extract": {"text", "docx", "pdf", "xlsx", "markdown"},
    "analyze": {"text", "chart", "docx", "html", "xlsx", "markdown", "report"},
    "transform": {"text", "docx", "html", "markdown", "document", "report"},
    "deliver": {"docx", "xlsx", "pptx", "html", "pdf", "text", "chart", "markdown", "document", "report"},
}
ROLE_OUTPUT_HINTS = {
    "collect": {"web", "text", "data", "results", "links", "json", "report", "chart"},
    "extract": {"text", "docx", "pdf", "xlsx", "markdown", "json", "report", "data"},
    "analyze": {"text", "chart", "docx", "html", "xlsx", "markdown", "report", "plans", "lists", "strategy", "campaign"},
    "transform": {"text", "docx", "html", "markdown", "document", "plans", "lists", "strategy", "copy", "report", "agenda", "confirmation"},
    "deliver": {"docx", "xlsx", "pptx", "html", "pdf", "text", "chart", "markdown", "document", "report", "web"},
    "review": {"text", "docx", "xlsx", "pptx", "html", "markdown", "report", "document", "plans", "lists", "confirmation", "chart"},
    "enhance": {"image", "html", "pptx", "chart", "audio", "mp3", "text", "document"},
    "publish": {"text", "html", "docx", "web", "image", "document"},
}
FILE_LIKE_INPUTS = {"pdf", "image", "audio", "docx", "xlsx", "pptx", "file", "document"}
TEXTUAL_OR_STRUCTURED_OUTPUTS = {"text", "docx", "html", "xlsx", "chart", "markdown", "report", "data", "results", "json", "document", "web"}
PRIMARY_DELIVERABLE_OUTPUTS = {"docx", "xlsx", "pptx", "html", "pdf", "text", "chart", "markdown", "document", "report"}
CROSS_DOMAIN_SUPPORTING_DOMAINS = {"research", "office", "general", "content"}
TOPIC_DOMAIN_KEYWORDS = TOPIC_TAXONOMY["topic_domain_keywords"]


def load_profiles(root: Path) -> dict[str, dict[str, Any]]:
    profiles = {}
    for path in sorted((root / "profiles").glob("*.json")):
        profile = load_json(path)
        if profile.get("task_eligible", True) is False:
            continue
        profiles[path.stem] = profile
    return profiles


def load_groups(root: Path) -> dict[str, dict[str, list[str]]]:
    groups = {}
    for path in sorted((root / "groups").glob("*.json")):
        groups[path.stem] = load_json(path).get("groups", {})
    return groups


def infer_topic_domains(topic: str) -> set[str]:
    topic = str(topic).strip()
    matches = set()
    for domain, keywords in TOPIC_DOMAIN_KEYWORDS.items():
        if any(keyword in topic for keyword in keywords):
            matches.add(domain)
    return matches or {"general"}


def role_priority(profile: dict[str, Any], role: str) -> int:
    roles = profile.get("allowed_roles") or profile.get("intent_roles", [])
    try:
        return roles.index(role)
    except ValueError:
        return 99


def slot_eligible(profile: dict[str, Any], role: str, slot_kind: str, chain_name: str) -> bool:
    allowed_roles = profile.get("allowed_roles") or profile.get("intent_roles", [])
    if role not in allowed_roles:
        return False
    if slot_kind == "required":
        if chain_name == "primary_chain":
            if profile.get("allow_primary_chain") is False or profile.get("allow_required_slots") is False:
                return False
        if chain_name != "primary_chain" and profile.get("allow_secondary_chain", True) is False:
            return False
    return True


def compatible(candidate: str, chosen: list[str], groups: dict[str, dict[str, list[str]]]) -> bool:
    for slug in chosen:
        bucket = groups.get(slug, {})
        substitutes = set(bucket.get("substitute", []))
        anti_patterns = set(bucket.get("anti_pattern", []))
        if candidate in substitutes or candidate in anti_patterns:
            return False
    return True


def dominant_domains(chosen: list[str], profiles: dict[str, dict[str, Any]]) -> set[str]:
    counts: dict[str, int] = {}
    for slug in chosen:
        for domain in profiles[slug].get("domain_tags", []):
            counts[domain] = counts.get(domain, 0) + 1
    if not counts:
        return set()
    top = max(counts.values())
    return {domain for domain, count in counts.items() if count == top and domain != "general"}


def domain_overlap(a: dict[str, Any], b: dict[str, Any]) -> int:
    return len(set(a.get("domain_tags", [])) & set(b.get("domain_tags", [])))


def artifact_affinity(a: dict[str, Any], b: dict[str, Any]) -> float:
    a_out = set(a.get("artifact_out", []))
    b_in = set(b.get("artifact_in", []))
    b_out = set(b.get("artifact_out", []))
    shared = len(a_out & b_in)
    if shared:
        return min(0.22, 0.11 * shared)
    same_output = len(a_out & b_out)
    if same_output and "publish" not in set(a.get("intent_roles", []) + b.get("intent_roles", [])):
        return 0.04
    return 0.0


def role_bucket_usage(slug: str, role: str, usage_by_role: dict[str, Counter[str]]) -> int:
    return usage_by_role.get(role, Counter()).get(slug, 0)


def recent_window_penalty(slug: str, role: str, recent_by_role: dict[str, deque[str]]) -> float:
    recent = list(recent_by_role.get(role, deque()))
    if not recent:
        return 0.0
    penalty = 0.0
    for idx, seen in enumerate(reversed(recent), start=1):
        if seen == slug:
            penalty += max(0.1, 0.55 - idx * 0.08)
    return penalty


def chain_role_bonus(profile: dict[str, Any], role: str, chain_name: str, template: dict[str, Any]) -> float:
    priority = role_priority(profile, role)
    score = 0.0
    artifact_out = set(profile.get("artifact_out", []))
    if chain_name == "primary_chain":
        if priority == 0:
            score += 0.28
        elif priority == 1:
            score += 0.08
        elif priority > 1:
            score -= 0.45
        if role == "collect":
            if {"web", "text"} & artifact_out:
                score += 0.12
            if {"audio", "image", "mp3"} & artifact_out and "web" not in artifact_out:
                score -= 0.18
        elif role == "deliver":
            if {"docx", "xlsx", "pptx", "html", "pdf", "text"} & artifact_out:
                score += 0.14
            if artifact_out == {"image"} or artifact_out == {"audio"} or artifact_out == {"mp3"}:
                score -= 0.28
        elif role == "analyze":
            if {"text", "chart", "docx", "html", "xlsx"} & artifact_out:
                score += 0.08
    elif chain_name == "secondary_chain":
        if priority == 0:
            score += 0.12
        elif priority > 1:
            score -= 0.12

    kind = template.get("secondary_chain_kind", "")
    allowed_roles = set(profile.get("allowed_roles") or profile.get("intent_roles", []))
    if chain_name == "secondary_chain":
        if kind == "source_check_support":
            if role == "collect" and "collect" in allowed_roles:
                score += 0.12
            if role == "review" and "review" in allowed_roles:
                score += 0.12
        elif kind == "refinement_for_decision":
            if role == "transform" and "transform" in allowed_roles:
                score += 0.12
            if role == "review" and "review" in allowed_roles:
                score += 0.05
        elif kind == "presentation_support":
            if role == "enhance" and ("enhance" in allowed_roles or {"image", "html", "chart"} & artifact_out):
                score += 0.14
            if role == "review" and "review" in allowed_roles:
                score += 0.03
        elif kind == "analysis_with_evidence_check":
            if role == "analyze" and "analyze" in allowed_roles:
                score += 0.12
            if role == "review" and "review" in allowed_roles:
                score += 0.05
        elif kind == "publish_support":
            if role == "publish" and "publish" in allowed_roles:
                score += 0.16
            if role == "review" and "review" in allowed_roles:
                score += 0.03
        elif kind == "refinement_presentation":
            if role == "review" and "review" in allowed_roles:
                score += 0.1
            if role == "enhance" and ("enhance" in allowed_roles or {"image", "html", "pptx"} & artifact_out):
                score += 0.14
    elif chain_name == "enhancement_chain":
        kind = template.get("enhancement_chain_kind", "")
        if kind == "presentation_support":
            if role == "enhance" and ("enhance" in allowed_roles or {"image", "html", "pptx", "chart"} & artifact_out):
                score += 0.18
            if role == "transform" and "transform" in allowed_roles:
                score += 0.08
        elif kind == "decision_support":
            if role == "transform" and "transform" in allowed_roles:
                score += 0.16
            if role == "publish" and "publish" in allowed_roles:
                score += 0.08
            if role == "enhance" and ("enhance" in allowed_roles or {"chart", "html"} & artifact_out):
                score += 0.06
        elif kind == "execution_support":
            if role == "transform" and "transform" in allowed_roles:
                score += 0.14
            if role == "enhance" and ("enhance" in allowed_roles or {"html", "chart"} & artifact_out):
                score += 0.05
        elif kind == "audience_adaptation":
            if role == "publish" and "publish" in allowed_roles:
                score += 0.16
            if role == "transform" and "transform" in allowed_roles:
                score += 0.08
    return score


def primary_role_guard(profile: dict[str, Any], role: str) -> float:
    artifact_out = set(profile.get("artifact_out", []))
    hints = PRIMARY_ROLE_OUTPUT_HINTS.get(role, set())
    if not hints:
        return 0.0
    if artifact_out & hints:
        return 0.1
    return -0.35


def role_output_match(profile: dict[str, Any], role: str) -> bool:
    return bool(set(profile.get("artifact_out", [])) & ROLE_OUTPUT_HINTS.get(role, set()))


def topic_domain_score(profile: dict[str, Any], topic_domains: set[str]) -> float:
    if not topic_domains or topic_domains == {"general"}:
        return 0.0
    domains = set(profile.get("domain_tags", []))
    overlap = domains & topic_domains
    if overlap:
        return 0.22
    if "general" in domains:
        return -0.08
    return -0.38


def topic_domain_eligible(profile: dict[str, Any], topic: str | None, chain_name: str, role: str) -> bool:
    if not topic:
        return True
    topic_domains = infer_topic_domains(topic)
    if not topic_domains or topic_domains == {"general"}:
        return True
    domains = set(profile.get("domain_tags", []))
    if domains & topic_domains:
        return True
    allowed_roles = set(profile.get("allowed_roles") or profile.get("intent_roles", []))
    artifact_out = set(profile.get("artifact_out", []))
    if chain_name == "primary_chain":
        if role == "deliver" and "deliver" in allowed_roles and artifact_out & PRIMARY_DELIVERABLE_OUTPUTS:
            return bool(domains & {"office", "research", "general", "government", "gov", "presentation", "finance", "analysis"})
        if role == "transform" and "transform" in allowed_roles and artifact_out & TEXTUAL_OR_STRUCTURED_OUTPUTS:
            return bool(domains & CROSS_DOMAIN_SUPPORTING_DOMAINS)
        return False
    if role == "publish" and "publish" in allowed_roles and role_output_match(profile, role):
        return True
    if role in {"review", "enhance", "deliver", "transform"} and domains & CROSS_DOMAIN_SUPPORTING_DOMAINS:
        return role_output_match(profile, role)
    if role in {"collect", "analyze"} and domains & CROSS_DOMAIN_SUPPORTING_DOMAINS:
        return bool(artifact_out & TEXTUAL_OR_STRUCTURED_OUTPUTS)
    return role not in {"collect", "analyze"}


def role_family_eligible(
    profile: dict[str, Any],
    role: str,
    chain_name: str,
    template: dict[str, Any] | None = None,
    topic: str | None = None,
) -> bool:
    artifact_in = set(profile.get("artifact_in", []))
    artifact_out = set(profile.get("artifact_out", []))
    domains = set(profile.get("domain_tags", []))
    allowed_roles = set(profile.get("allowed_roles") or profile.get("intent_roles", []))
    primary_slot = chain_name == "primary_chain"

    if role == "collect":
        return (
            "collect" in allowed_roles
            and role_output_match(profile, role)
            and bool((artifact_in & {"web", "query", "url", "text"}) or (artifact_out & {"web", "text", "data", "results", "report"}))
            and not artifact_out <= {"audio", "mp3", "image"}
        )
    if role == "extract":
        return (
            "extract" in allowed_roles
            and bool(artifact_in & FILE_LIKE_INPUTS)
            and role_output_match(profile, role)
        )
    if role == "transform":
        return (
            "transform" in allowed_roles
            and role_output_match(profile, role)
            and (not primary_slot or bool(artifact_out & TEXTUAL_OR_STRUCTURED_OUTPUTS))
            and (not primary_slot or not artifact_out <= {"audio", "mp3", "image"})
        )
    if role == "analyze":
        return (
            "analyze" in allowed_roles
            and role_output_match(profile, role)
            and bool(domains & {"research", "finance", "office", "government", "gov", "general", "content", "analysis", "business", "strategy"})
            and (not primary_slot or not artifact_out <= {"audio", "mp3", "image"})
        )
    if role == "deliver":
        return (
            "deliver" in allowed_roles
            and role_output_match(profile, role)
            and (not primary_slot or bool(artifact_out & PRIMARY_DELIVERABLE_OUTPUTS))
            and (not primary_slot or not artifact_out <= {"audio", "mp3", "image"})
            and (
                not primary_slot
                or bool(domains & {"research", "finance", "office", "government", "gov", "general", "analysis", "presentation"})
                or bool(artifact_out & {"docx", "xlsx", "pptx", "pdf"})
            )
        )
    if role == "review":
        return "review" in allowed_roles and role_output_match(profile, role)
    if role == "enhance":
        return "enhance" in allowed_roles and role_output_match(profile, role)
    if role == "publish":
        return "publish" in allowed_roles and bool(artifact_out & {"text", "html", "docx", "web", "image"})
    return True


def candidate_score(
    profile: dict[str, Any],
    role: str,
    chosen: list[str],
    profiles: dict[str, dict[str, Any]],
    usage_by_role: dict[str, Counter[str]],
    recent_by_role: dict[str, deque[str]],
    chain_name: str,
    template: dict[str, Any],
    topic: str | None = None,
) -> float:
    score = 0.0
    topic_domains = infer_topic_domains(topic) if topic else {"general"}
    score += 1.0 if role in profile.get("intent_roles", []) else 0.0
    score += max(0, 0.35 - 0.1 * role_priority(profile, role))
    score += chain_role_bonus(profile, role, chain_name, template)
    if chain_name == "primary_chain":
        score += primary_role_guard(profile, role)
    if topic:
        score += topic_domain_score(profile, topic_domains)
    current_domains = dominant_domains(chosen, profiles)
    candidate_domains = set(profile.get("domain_tags", []))
    if current_domains:
        if current_domains & candidate_domains:
            score += 0.28
        elif "general" not in candidate_domains:
            score -= 0.45
    elif "general" not in candidate_domains:
        score += 0.05
    coherent = False
    for slug in chosen:
        anchor = profiles[slug]
        score += domain_overlap(profile, anchor) * 0.08
        forward = artifact_affinity(anchor, profile)
        backward = artifact_affinity(profile, anchor) * 0.5
        score += forward
        score += backward
        coherent = coherent or forward > 0 or backward > 0 or domain_overlap(profile, anchor) > 0
    if chosen and coherent:
        score += 0.18
    if chosen and not coherent and role not in {"enhance", "publish"}:
        score -= 0.6
    score -= role_bucket_usage(profile["slug"], role, usage_by_role) * 0.32
    score -= recent_window_penalty(profile["slug"], role, recent_by_role)
    return score


def pick_best_candidate(
    role: str,
    chosen: list[str],
    profiles: dict[str, dict[str, Any]],
    groups: dict[str, dict[str, list[str]]],
    usage_by_role: dict[str, Counter[str]],
    recent_by_role: dict[str, deque[str]],
    rng: random.Random,
    template: dict[str, Any],
    chain_name: str,
    slot_kind: str,
    min_score: float | None = 0.35,
    topic: str | None = None,
) -> str | None:
    candidates = []
    for slug, profile in profiles.items():
        if slug in chosen:
            continue
        if not slot_eligible(profile, role, slot_kind, chain_name):
            continue
        if not role_family_eligible(profile, role, chain_name, template, topic):
            continue
        if not topic_domain_eligible(profile, topic, chain_name, role):
            continue
        if not compatible(slug, chosen, groups):
            continue
        score = candidate_score(profile, role, chosen, profiles, usage_by_role, recent_by_role, chain_name, template, topic)
        if min_score is not None and chosen and score < min_score:
            continue
        candidates.append((score, slug))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    head = candidates[: min(4, len(candidates))]
    return rng.choice(head)[1]


def coverage_summary(chosen: list[str], profiles: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    roles = []
    domains = []
    artifacts = []
    for slug in chosen:
        profile = profiles[slug]
        roles.extend(profile.get("intent_roles", []))
        domains.extend(profile.get("domain_tags", []))
        artifacts.extend(profile.get("artifact_out", []))
    return {
        "roles": sorted(set(roles)),
        "domains": sorted(set(domains)),
        "artifacts": sorted(set(artifacts)),
    }


def sample_role_sequence(
    roles: list[str],
    chosen: list[str],
    profiles: dict[str, dict[str, Any]],
    groups: dict[str, dict[str, list[str]]],
    usage_by_role: dict[str, Counter[str]],
    recent_by_role: dict[str, deque[str]],
    rng: random.Random,
    template: dict[str, Any],
    chain_name: str,
    topic: str | None = None,
) -> list[dict[str, str]]:
    slots = []
    for role in roles:
        slug = pick_best_candidate(role, chosen, profiles, groups, usage_by_role, recent_by_role, rng, template, chain_name, slot_kind="required", min_score=None, topic=topic)
        if slug is None:
            raise RuntimeError(f"unable to fill required role {role} for {chain_name}")
        chosen.append(slug)
        slots.append({"role": role, "slug": slug, "chain": chain_name})
        usage_by_role[role][slug] += 1
        recent_by_role[role].append(slug)
    return slots


def sample_preferred_role_sequence(
    roles: list[str],
    chosen: list[str],
    profiles: dict[str, dict[str, Any]],
    groups: dict[str, dict[str, list[str]]],
    usage_by_role: dict[str, Counter[str]],
    recent_by_role: dict[str, deque[str]],
    rng: random.Random,
    template: dict[str, Any],
    chain_name: str,
    topic: str | None = None,
    min_required: int = 1,
) -> list[dict[str, str]]:
    slots = []
    for role in roles:
        slug = pick_best_candidate(role, chosen, profiles, groups, usage_by_role, recent_by_role, rng, template, chain_name, slot_kind="required", min_score=None, topic=topic)
        if slug is None:
            continue
        chosen.append(slug)
        slots.append({"role": role, "slug": slug, "chain": chain_name})
        usage_by_role[role][slug] += 1
        recent_by_role[role].append(slug)
    if len(slots) < min_required:
        raise RuntimeError(f"unable to fill enough roles for {chain_name}")
    return slots


def sample_bundle(
    template: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
    groups: dict[str, dict[str, list[str]]],
    usage_by_role: dict[str, Counter[str]],
    recent_by_role: dict[str, deque[str]],
    rng: random.Random,
    topic: str | None = None,
) -> dict[str, Any]:
    chosen: list[str] = []
    used_roles: set[str] = set()

    primary_chain = sample_role_sequence(
        template.get("primary_chain_roles", []),
        chosen,
        profiles,
        groups,
        usage_by_role,
        recent_by_role,
        rng,
        template,
        "primary_chain",
        topic,
    )
    secondary_chain = sample_role_sequence(
        template.get("secondary_chain_roles", []),
        chosen,
        profiles,
        groups,
        usage_by_role,
        recent_by_role,
        rng,
        template,
        "secondary_chain",
        topic,
    )
    try:
        enhancement_chain = sample_preferred_role_sequence(
            template.get("enhancement_chain_roles", []),
            chosen,
            profiles,
            groups,
            usage_by_role,
            recent_by_role,
            rng,
            template,
            "enhancement_chain",
            topic,
            min_required=1,
        )
    except RuntimeError:
        # Keep primary/secondary chains topic-aligned; only relax enhancement fill
        # when a topic-specific tail role becomes too narrow.
        try:
            enhancement_chain = sample_preferred_role_sequence(
                template.get("enhancement_chain_roles", []),
                chosen,
                profiles,
                groups,
                usage_by_role,
                recent_by_role,
                rng,
                template,
                "enhancement_chain",
                None,
                min_required=1,
            )
        except RuntimeError:
            enhancement_chain = []

    for item in primary_chain + secondary_chain + enhancement_chain:
        used_roles.add(item["role"])

    optional_hits = []
    for role in template.get("support_roles", []):
        if rng.random() < 0.65:
            slug = pick_best_candidate(role, chosen, profiles, groups, usage_by_role, recent_by_role, rng, template, "support_chain", slot_kind="support", min_score=0.35, topic=topic)
            if slug is not None:
                chosen.append(slug)
                optional_hits.append({"role": role, "slug": slug, "chain": "support_chain"})
                used_roles.add(role)
                usage_by_role[role][slug] += 1
                recent_by_role[role].append(slug)

    support_priority = ["enhance", "review", "publish", "deliver", "transform", "analyze"]
    target_skill_count = max(7, len(primary_chain) + len(secondary_chain) + len(enhancement_chain) + 1)
    for role in support_priority:
        if len(chosen) >= target_skill_count:
            break
        if role in used_roles and role not in {"enhance", "review", "publish"}:
            continue
        slug = pick_best_candidate(role, chosen, profiles, groups, usage_by_role, recent_by_role, rng, template, "support_chain", slot_kind="support", min_score=0.35, topic=topic)
        if slug is None:
            continue
        chosen.append(slug)
        optional_hits.append({"role": role, "slug": slug, "chain": "support_chain"})
        used_roles.add(role)
        usage_by_role[role][slug] += 1
        recent_by_role[role].append(slug)

    return {
        "template": template["name"],
        "description": template.get("description", ""),
        "secondary_chain_kind": template.get("secondary_chain_kind", ""),
        "enhancement_chain_kind": template.get("enhancement_chain_kind", ""),
        "primary_chain": primary_chain,
        "secondary_chain": secondary_chain,
        "enhancement_chain": enhancement_chain,
        "support_slots": optional_hits,
        "skills": chosen,
        "coverage": coverage_summary(chosen, profiles),
    }


def usage_summary(usage_by_role: dict[str, Counter[str]]) -> dict[str, list[dict[str, Any]]]:
    summary: dict[str, list[dict[str, Any]]] = {}
    for role, counter in sorted(usage_by_role.items()):
        rows = [{"slug": slug, "count": count} for slug, count in counter.most_common()]
        summary[role] = rows
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sample coherent skill bundles from experimental step0 shards.")
    parser.add_argument("--artifacts-root", type=Path, default=ARTIFACTS_ROOT)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=None)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    profiles = load_profiles(args.artifacts_root)
    groups = load_groups(args.artifacts_root)
    templates = load_json(args.artifacts_root / "task_templates.json").get("templates", [])
    rng = random.Random(args.seed)
    usage_by_role: dict[str, Counter[str]] = defaultdict(Counter)
    recent_by_role: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=6))

    bundles = []
    for idx in range(args.count):
        template = templates[idx % len(templates)]
        bundles.append(sample_bundle(template, profiles, groups, usage_by_role, recent_by_role, rng))

    output = {
        "seed": args.seed,
        "count": args.count,
        "bundles": bundles,
        "usage_by_role": usage_summary(usage_by_role),
    }
    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
