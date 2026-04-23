#!/usr/bin/env python3
"""
Audit experimental skill profiles and output JSON for review.

This script loads all profiles from artifacts/profiles/ and outputs them
in a structured JSON format suitable for the calling model to review
the classifications directly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXP_ROOT = Path(__file__).resolve().parent
ARTIFACTS_ROOT = EXP_ROOT / "artifacts"


def load_profiles(root: Path) -> list[dict[str, Any]]:
    profiles = []
    for path in sorted((root / "profiles").glob("*.json")):
        profiles.append(json.loads(path.read_text(encoding="utf-8")))
    return profiles


def summarize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Extract the key classification fields for review."""
    return {
        "slug": profile.get("slug", ""),
        "name": profile.get("name", ""),
        "description": profile.get("description", ""),
        "intent_roles": profile.get("intent_roles", []),
        "allowed_roles": profile.get("allowed_roles", []),
        "domain_tags": profile.get("domain_tags", []),
        "artifact_in": profile.get("artifact_in", []),
        "artifact_out": profile.get("artifact_out", []),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export skill profile summaries as JSON for model-based auditing."
    )
    parser.add_argument("--artifacts-root", type=Path, default=ARTIFACTS_ROOT)
    parser.add_argument("--limit", type=int, default=0, help="Max profiles to output (0 = all)")
    parser.add_argument("--slugs", nargs="*", default=None, help="Only output these specific slugs")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    profiles = load_profiles(args.artifacts_root)

    if args.slugs:
        slug_set = set(args.slugs)
        profiles = [p for p in profiles if p.get("slug") in slug_set]

    summaries = [summarize_profile(p) for p in profiles]

    if args.limit > 0:
        summaries = summaries[: args.limit]

    print(json.dumps({"total": len(summaries), "profiles": summaries}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
