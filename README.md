# Experimental Step0/Step1

This directory contains an isolated prototype for a more incremental `step0` and a template-driven `step1`.
It does not modify the repository's existing `references/skill_compatibility.json`.

## Goal

Instead of producing one monolithic compatibility graph, this experiment builds:

- per-skill profiles
- per-skill substitution and anti-pattern groups
- a task-template registry for `step1` sampling

The current design target is to let `step1` sample by intent roles, domain coherence, lightweight artifact affinity, per-role balancing, and an LLM bundle judge before hidden-plan generation.

## Files

- `step0_incremental_index.py`: experimental builder
- `step1_skeleton_sampler.py`: experimental sampler built on top of the shards
- `step1_generate_hidden_plans.py`: experimental step1 JSONL generator
- `audit_profiles.py`: flag suspicious profile classifications
- `references/manual_overrides.json`: optional manual corrections for obviously misclassified skills
- `artifacts/profiles/<slug>.json`: skill profile shard
- `artifacts/groups/<slug>.json`: substitute and anti-pattern groups for `<slug>`
- `artifacts/task_templates.json`: task skeletons
- `artifacts/manifest.json`: run metadata and updated slugs

## Example

Create or edit the project-local `.env` first:

```bash
cp gpt-exp/.env.example gpt-exp/.env
```

Then fill in at least:

```bash
OPENAI_MODEL=glm-5.1
OPENAI_API_BASE=https://open.bigmodel.cn/api/paas/v4/
OPENAI_API_KEY=...
OPENAI_TIMEOUT=120
SKILLS_POOL=/abs/path/to/skills-selected
```

Run a full build:

```bash
python gpt-exp/step0_incremental_index.py --all
```

Refresh a single skill after adding it to the pool:

```bash
python gpt-exp/step0_incremental_index.py --refresh-skill my-new-skill
```

Sample a few skill bundles from the generated shards:

```bash
python gpt-exp/step1_skeleton_sampler.py --count 5
```

Generate experimental step1 records:

```bash
python gpt-exp/step1_generate_hidden_plans.py 12
```

The step1 generator now does:

- initial bundle sampling
- full-bundle LLM judging with fixed subscores
- whole-bundle resampling on judge failure
- fallback accept of the highest-scoring attempt when retries are exhausted

Judge policy can be tuned from `.env`:

```bash
STEP1_JUDGE_MAX_RESAMPLES=3
STEP1_JUDGE_PASS_THRESHOLD=19
STEP1_JUDGE_SINGLE_GOAL_FLOOR=4
STEP1_JUDGE_ROLE_CHAIN_FLOOR=4
STEP1_JUDGE_NATURALNESS_FLOOR=4
```

Audit suspicious profiles before trusting the sampler:

```bash
python gpt-exp/audit_profiles.py --limit 20
```

Run local compile + no-network smoke checks before hitting real APIs:

```bash
python gpt-exp/run_local_smoke_checks.py
```

By default the scripts auto-load `gpt-exp/.env`, then fall back to environment variables.
`step0` / `step1` / `step2` / `step3` all now share the same OpenAI defaults and timeout handling.
For a direct shell export flow, set:

```bash
export OPENAI_API_BASE="https://open.bigmodel.cn/api/paas/v4/"
export OPENAI_MODEL="glm-5.1"
export OPENAI_API_KEY="..."
```

The script also accepts model names like `openai/glm-5.1` and will normalize them to `glm-5.1` before sending the request.

`step0_incremental_index.py` now requires LLM access and no longer provides a heuristic-only fallback mode.
You can still keep a small `references/manual_overrides.json` file for edge-case skills whose roles or artifact tags need explicit correction.

Generated artifacts are written under `outputs/`, `workspace_outputs/`, and `artifacts/`; these are intended as build/runtime outputs rather than hand-edited source files.
