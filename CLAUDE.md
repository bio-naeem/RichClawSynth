# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repository is an experimental benchmark-query synthesis pipeline. Its core design is:

1. build an **incremental skill index** instead of one monolithic compatibility graph
2. sample **skill bundles from task templates and role slots**
3. generate a structured hidden plan
4. rewrite that plan into a richer natural-language user query
5. optionally materialize workspaces for downstream execution/evaluation

The important mental model is that difficulty is meant to come from the **execution structure** of the sampled skill chain, not from making the final user query artificially verbose.

## Common commands

## Environment setup

```bash
cp .env.example .env
# then fill in OPENAI_API_KEY and related OpenAI/OpenAI-compatible settings
```

Most scripts auto-load `.env` via `pipeline_common.load_project_dotenv()`.

## Main pipeline commands

### Build or refresh the incremental index (step0)
```bash
python step0_incremental_index.py --all
python step0_incremental_index.py --refresh-skill my-new-skill
```

### Sample bundles only
```bash
python step1_skeleton_sampler.py --count 5
```

### Generate hidden-plan records (step1)
```bash
python step1_generate_hidden_plans.py 12
```

### Rewrite records into richer user queries (step2)
```bash
python step2_rewrite_richer.py inputs/step1.jsonl outputs/step2.jsonl
```

### Naturalize/diversify the rewritten queries (step3)
```bash
python step3_naturalize_diversify.py outputs/step2.jsonl outputs/step3.jsonl
```

### Materialize workspaces from generated JSONL (step4)
```bash
python step4_build_workspaces.py outputs/step3.jsonl --tag demo --force
```

### Run the end-to-end pipeline (steps 1-4)
```bash
bash run_e2e_pipeline.sh 10 demo
```

This runs:
- `step1_generate_hidden_plans.py`
- `step2_rewrite_richer.py`
- `step3_naturalize_diversify.py`
- `step4_build_workspaces.py`

and writes outputs under `outputs/` plus workspace materialization under `workspace_outputs/`.

## Validation commands

### Audit suspicious profile classifications
```bash
python audit_profiles.py --limit 20
```

### Run local no-network smoke checks
```bash
python run_local_smoke_checks.py
```

This is the closest thing to a repo-wide validation command. It runs:
- `py_compile` on the main pipeline scripts
- a sampler smoke test
- an in-process step1 → step2 → step3 smoke path using a dummy client

### Run a single test file for the bundled file-generator skill
```bash
python -m unittest discover -s .agent/skills/claw-input-file-generator/tests -p 'test_contract.py'
```

## Architecture

## Big picture

The main pipeline is split into four conceptual layers:

1. **Indexing layer**: converts each skill into shard-like metadata files
2. **Sampling/planning layer**: assembles balanced, role-compatible bundles and emits structured hidden plans
3. **Query-writing layer**: turns hidden plans into user-facing benchmark queries in two passes
4. **Workspace materialization layer**: builds runnable workspaces from the generated records

The runtime glue for all LLM-backed stages lives in `pipeline_common.py`.

## Shared runtime layer

`pipeline_common.py` is the common foundation for the pipeline scripts.

It centralizes:
- `.env` loading
- JSON / JSONL read-write helpers
- OpenAI-compatible client construction
- retry handling for transient LLM/API failures
- model-name normalization and shared CLI args

When changing any LLM-backed step, check `pipeline_common.py` first before re-implementing client or retry logic locally.

## Step0: per-skill shard generation

`step0_incremental_index.py` reads a skills pool and expects each skill directory to contain `SKILL.md` frontmatter. It extracts metadata, calls the LLM to build a normalized profile, and writes shard outputs under `artifacts/`.

Important outputs:
- `artifacts/profiles/<slug>.json`: normalized skill profile
- `artifacts/groups/<slug>.json`: substitution / anti-pattern relations
- `artifacts/task_templates.json`: task template registry used by sampling
- `artifacts/manifest.json`: index metadata including indexed skills

Important implementation detail: this step is not just “classification”. It also soft-demotes meta-orchestration skills and derives the compatibility/grouping primitives that later sampling depends on.

Manual corrections live in:
- `references/manual_overrides.json`

## Step1: bundle sampling and hidden-plan generation

There are two separate pieces here:

- `step1_skeleton_sampler.py`: samples bundles from template role slots using profiles + groups
- `step1_generate_hidden_plans.py`: turns those sampled bundles into step1 JSONL records

The sampler logic is template-driven, not graph-driven. Templates define required role chains such as primary / secondary / enhancement / support slots. Sampling then balances usage by role, filters conflicts via group data, and relaxes constraints only when needed.

`step1_generate_hidden_plans.py` adds the higher-level record structure:
- topic schedule
- persona selection
- input-context scheduling
- hidden-plan generation
- derived constraints such as `global_constraints` and `delivery_layers`

This is the stage where the pipeline moves from “which skills fit together?” to “what benchmark task structure should this sample express?”

## Step2 and Step3: two-pass query writing

The user-visible benchmark query is not generated in one shot.

### Step2
`step2_rewrite_richer.py` rewrites the structured step1 record into a richer task request while preserving complexity, delivery structure, review points, and persona/location constraints.

### Step3
`step3_naturalize_diversify.py` rewrites the step2 query again to make it sound more like a real user request, while keeping key structural constraints intact.

This separation is important: step2 preserves task semantics; step3 mainly improves surface naturalness and stylistic diversity.

Prompt templates for these two passes live in:
- `prompts_step2_exp.py`
- `prompts_step3_exp.py`

## Step4: workspace materialization

`step4_build_workspaces.py` converts step2/step3 JSONL records into lightweight workspace bundles under `workspace_outputs/`.

It symlinks the selected skills into each workspace and writes per-workspace metadata derived from fields like:
- `chain_design`
- `chain_skills`
- `hidden_plan`
- `global_constraints`
- `delivery_layers`

This stage is what bridges generated benchmark records into something that can be executed or evaluated downstream.

## Experimental file-generation path

`step5_file_generate.py` is a separate batch-oriented workflow for pre-generating required input files in workspaces using OpenClaw and the bundled `claw-input-file-generator` skill.

Treat it as an operational/experimental extension, not part of the core step0→step4 path.

## Key data and config locations

- `artifacts/`: generated index shards and template registry
- `outputs/`: JSONL outputs from step1/step2/step3
- `workspace_outputs/`: materialized workspaces from step4
- `references/manual_overrides.json`: manual profile corrections
- `references/topics_narrowed.txt`: topic source for step1 scheduling
- `config/topic_taxonomy.json`: topic-dependent heuristics used by step1

Generated outputs under `artifacts/`, `outputs/`, and `workspace_outputs/` are build/runtime artifacts, not primary hand-edited source files.

## Repo-local agent skills

This repository also contains repo-local agent assets under `.agent/`.

Notably:
- `.agent/skills/synth-pipeline/SKILL.md`: canonical repo-local skill definition for running this synthesis pipeline
- `.agent/workflows/synth-pipeline.md`: compatibility stub pointing to the canonical skill

If you need to update the repo-local synth-pipeline skill, edit the canonical `SKILL.md`, not the workflow stub.
