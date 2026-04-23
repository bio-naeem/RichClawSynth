---
name: synth-pipeline
description: Run this repository's benchmark query synthesis pipeline, including optional skill index refresh, profile audit, end-to-end sample generation (Step 1-4), and background input-file generation (Step 5). Use this skill when the user wants to run or rerun the pipeline, generate benchmark samples/workspaces, or check newly added skills before generation.
---

# Synth Pipeline

A skill for operating the benchmark query synthesis pipeline in this repository.

At a high level, the process goes like this:

- Figure out which part of the pipeline the user actually wants to run
- Confirm missing inputs such as COUNT, TAG, or whether new skills should be included
- Check prerequisites only for the steps that are actually needed
- If requested, detect newly added skills and refresh step0
- If requested, audit new profiles and surface classification problems
- If requested, run step1 to step4 and report the generated outputs (JSONL + Workspaces)
- If requested, run step5 (run_step5.sh) to pre-generate input files in the workspaces in the background

Your job when using this skill is to understand where the user is in that process and move them forward without expanding scope on your own.

## Determine scope first

Start by identifying which of these cases applies:

1. **Generate samples only**
   - The user wants step1 to step4 outputs
   - Confirm `COUNT`
   - Use `TAG` if provided; otherwise default to `demo`
   - Do not add a step0 refresh unless the user asks for it

2. **Refresh index only**
   - The user wants newly added skills indexed
   - Check for unindexed skills
   - Refresh step0 only after confirming the intended scope

3. **Full pipeline (Step 1-5)**
   - The user explicitly wants the whole flow: check new skills, refresh index, audit profiles, generate samples, build workspaces, and then trigger background file generation.

## Confirm required inputs

- `COUNT` is required for generation
- `TAG` is optional and defaults to `demo`
- `SKILLS_POOL` defaults to `<repo-root>/skills-selected`

## Command reference

### Check for new skills
```bash
python3 -c "import os, json; m = json.load(open('artifacts/manifest.json')); indexed = set(m.get('indexed_skills', [])); on_disk = {d for d in os.listdir(os.environ.get('SKILLS_POOL', 'skills-selected')) if os.path.isdir(os.path.join(os.environ.get('SKILLS_POOL', 'skills-selected'), d))}; diff = on_disk - indexed; print(f'New skills: {diff}')"
```

### Refresh index (Step 0)
```bash
python3 step0_incremental_index.py --all
```

### Audit selected profiles
```bash
python3 audit_profiles.py --slugs <slug1> <slug2> ...
```

### Run Full E2E Pipeline (Step 1-4)
```bash
bash run_e2e_pipeline.sh <COUNT> <TAG>
```

### Background File Generation (Step 5)
Run this after step4 is complete to pre-generate required input files (images, docs, etc.) in the workspaces.
```bash
bash run_step5.sh
```

## Output expectations

When this skill completes, your response should include:
- What scope was executed
- Output JSONL paths (Step 1, 2, 3)
- **Workplace bundle path**: `workspace_outputs/<TAG>/<TAG>-work/`
- **File generation status**: Whether background file generation (Step 5) was triggered
- Any issues found during profile audit
