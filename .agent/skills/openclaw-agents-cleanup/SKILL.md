---
name: openclaw-agents-cleanup
description: Clean up openclaw agents by deleting all agents except specified ones (defaults to keeping 'main'). Use when the user wants to clean up, delete, or remove openclaw agents, or when they mention "agents list" and want to prune unused ones.
---

# OpenClaw Agents Cleanup

This skill helps clean up openclaw agents by deleting all agents except the ones you want to keep.

## Default Behavior

- Lists all current agents using `openclaw agents list`
- Keeps `main` agent by default (the default agent)
- Deletes all other agents using `openclaw agents delete <agent_name> --force`
- Shows final list to confirm cleanup

## Usage

The user can specify which agents to keep:

- "清理agents" → keeps only `main`, deletes everything else
- "除了 main 和 generator 都删了" → keeps `main` and `generator`, deletes the rest
- "只保留 workspace_001" → keeps only `workspace_001`, deletes everything else including `main`

## Workflow

1. Run `openclaw agents list` to see all agents
2. Parse the output to identify agent names
3. Determine which agents to keep based on user input (default: `main`)
4. Delete each agent not in the keep list using `openclaw agents delete <name> --force`
5. Run `openclaw agents list` again to verify the cleanup

## Notes

- Deletion uses `--force` flag to skip confirmation prompts
- If an agent is not found during deletion (already deleted), continue with the remaining ones
- Run deletions in batches for efficiency, but check results after each batch
- Some deletions may run in the background; verify with a final list command
