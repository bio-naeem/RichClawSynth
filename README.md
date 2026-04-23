# RichClawSynth

A benchmark query synthesis pipeline for generating complex, multi-skill task queries from skill bundles and task templates.

## Overview

RichClawSynth generates realistic benchmark queries by:

1. Building an **incremental skill index** from a skills pool
2. Sampling **skill bundles** based on task templates and role slots
3. Generating structured **hidden plans** for each bundle
4. Rewriting plans into natural **user-facing queries**
5. Materializing **workspaces** for downstream evaluation

The key design principle: difficulty comes from the **execution structure** of the sampled skill chain, not from artificially verbose queries.

## Features

- **Incremental Indexing**: Per-skill profiles and compatibility groups instead of monolithic graphs
- **Template-Driven Sampling**: Role-based skill bundle generation with conflict detection
- **Multi-Pass Query Writing**: Structured hidden plans → rich queries → naturalized queries
- **Workspace Materialization**: Ready-to-use workspace bundles for evaluation
- **LLM-Powered**: Uses OpenAI-compatible APIs for profile generation and query synthesis

## Using with AI Agents (Recommended)

This repository includes a built-in skill for AI agents (Claude Code, Cursor, etc.) to help operate the pipeline. This is the **recommended way** to use RichClawSynth.

### synth-pipeline Skill

Located at `.agent/skills/synth-pipeline/SKILL.md`, this skill enables AI agents to:

- Detect and refresh newly added skills in your skills pool
- Audit profile classifications for suspicious results
- Run the full pipeline (Step 1-4) with proper configuration
- Trigger background file generation (Step 5)
- Guide you through each step with appropriate confirmations

### Quick Example

Simply tell your AI agent what you want to do:

```
"Run the pipeline to generate 20 benchmark samples with tag 'experiment'"
```

```
"Check if there are new skills in my pool and refresh the index"
```

```
"Generate input files for the workspaces"
```

The agent will automatically use the `synth-pipeline` skill to execute the appropriate steps.

### Manual Usage

If you prefer to run commands manually, see the [Quick Start](#quick-start) section below.

## Installation

### Prerequisites

- Python 3.10+
- An OpenAI-compatible API (OpenAI, Azure, GLM, Qwen, etc.)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/bio-naeem/RichClawSynth.git
cd RichClawSynth
```

2. Create and configure environment:
```bash
cp .env.example .env
```

3. Edit `.env` with your settings:
```bash
OPENAI_MODEL=your-model-name
OPENAI_API_BASE=https://your-api-endpoint/
OPENAI_API_KEY=your-api-key
OPENAI_TIMEOUT=120
SKILLS_POOL=/path/to/your/skills-pool
```

## Quick Start

### Run the Full Pipeline

```bash
bash run_e2e_pipeline.sh 10 demo
```

This runs steps 1-4 and generates:
- `outputs/step1_hidden_plans_10_demo.jsonl`
- `outputs/step2_rewritten_10_demo.jsonl`
- `outputs/step3_naturalized_10_demo.jsonl`
- `workspace_outputs/demo/demo-work/`

### Individual Steps

**Step 0: Build/Refresh Skill Index**
```bash
# Build index for all skills
python step0_incremental_index.py --all

# Refresh a single skill
python step0_incremental_index.py --refresh-skill my-skill
```

**Step 1: Generate Hidden Plans**
```bash
python step1_generate_hidden_plans.py 12
```

**Step 2: Rewrite to Richer Queries**
```bash
python step2_rewrite_richer.py inputs/step1.jsonl outputs/step2.jsonl
```

**Step 3: Naturalize Queries**
```bash
python step3_naturalize_diversify.py outputs/step2.jsonl outputs/step3.jsonl
```

**Step 4: Build Workspaces**
```bash
python step4_build_workspaces.py outputs/step3.jsonl --tag demo --force
```

**Step 5: Generate Input Files (Optional)**
```bash
bash run_step5.sh
```

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Skills Pool                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 0: Incremental Index                                      │
│  - Parse SKILL.md frontmatter                                   │
│  - Generate LLM-based profiles                                  │
│  - Build substitution/anti-pattern groups                       │
│  - Create task template registry                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: Bundle Sampling & Hidden Plan Generation               │
│  - Sample skill bundles by role slots                           │
│  - LLM-based bundle judging                                     │
│  - Generate structured hidden plans                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: Rich Query Rewrite                                     │
│  - Preserve task complexity                                     │
│  - Maintain delivery structure                                  │
│  - Keep global constraints                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: Naturalization & Diversification                       │
│  - Make queries sound natural                                   │
│  - Add stylistic variety                                        │
│  - Preserve structural constraints                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 4: Workspace Materialization                              │
│  - Create workspace directories                                 │
│  - Symlink required skills                                      │
│  - Write metadata files                                         │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_MODEL` | Model name for LLM calls | `glm-5.1` |
| `OPENAI_API_BASE` | API endpoint URL | `https://open.bigmodel.cn/api/paas/v4/` |
| `OPENAI_API_KEY` | API key (required) | - |
| `OPENAI_TIMEOUT` | Request timeout in seconds | `120` |
| `SKILLS_POOL` | Path to skills directory | `./skills-selected` |
| `PERSONAS_PATH` | Path to personas JSONL | `./references/user_scenarios.jsonl` |

### Step 1 Judge Policy

```bash
STEP1_JUDGE_MAX_RESAMPLES=3      # Max resample attempts
STEP1_JUDGE_PASS_THRESHOLD=19    # Minimum score to pass
STEP1_JUDGE_SINGLE_GOAL_FLOOR=4  # Min single-goal score
STEP1_JUDGE_ROLE_CHAIN_FLOOR=4   # Min role-chain score
STEP1_JUDGE_NATURALNESS_FLOOR=4  # Min naturalness score
```

## Project Structure

```
RichClawSynth/
├── config/
│   ├── task_templates.json      # Task template definitions
│   └── topic_taxonomy.json      # Topic-dependent heuristics
├── references/
│   ├── manual_overrides.example.json    # Example profile corrections
│   ├── topics_narrowed.txt      # Topic source for step1
│   └── user_scenarios.jsonl     # Persona definitions
├── artifacts/                   # Generated index (gitignored)
│   ├── profiles/
│   ├── groups/
│   └── manifest.json
├── outputs/                     # Pipeline outputs (gitignored)
├── workspace_outputs/           # Materialized workspaces (gitignored)
├── step0_incremental_index.py   # Build skill index
├── step1_skeleton_sampler.py    # Sample skill bundles
├── step1_generate_hidden_plans.py
├── step2_rewrite_richer.py
├── step3_naturalize_diversify.py
├── step4_build_workspaces.py
├── step5_file_generate.py       # Optional input file generation
├── pipeline_common.py           # Shared utilities
├── prompts_step2_exp.py         # Step 2 prompt templates
├── prompts_step3_exp.py         # Step 3 prompt templates
├── run_e2e_pipeline.sh          # End-to-end runner
└── run_step5.sh                 # Step 5 runner
```

## Validation

### Audit Profiles

Flag suspicious skill classifications:

```bash
python audit_profiles.py --limit 20
```

### Smoke Checks

Run local validation without network calls:

```bash
python run_local_smoke_checks.py
```

## API Compatibility

The pipeline supports any OpenAI-compatible API:

- **OpenAI**: `https://api.openai.com/v1/`
- **Azure OpenAI**: `https://your-resource.openai.azure.com/`
- **GLM (Zhipu)**: `https://open.bigmodel.cn/api/paas/v4/`
- **Qwen (Alibaba)**: `https://dashscope.aliyuncs.com/compatible-mode/v1/`
- **Local models**: Any local server implementing the OpenAI API

Model names with prefixes (e.g., `openai/gpt-4`, `qwen/qwen3.6-plus`) are automatically normalized.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

This project builds on concepts from skill-based agent evaluation and benchmark synthesis research.
