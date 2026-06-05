# Inspect Skills

Coding agent skills for Inspect AI and its ecosystem (`inspect_ai`, `inspect_evals`, `inspect_flow`, `inspect_scout`, `inspect_viz`, `inspect_swe`, `inspect_harbor`, sandboxes).

## Install

### Global (recommended)

```bash
npx skills add meridianlabs-ai/inspect-skills --agent claude-code -g -y
```

### Single project only

```bash
# run from the project root
npx skills add meridianlabs-ai/inspect-skills --agent claude-code -y
```

`-y` installs every skill in the repo non-interactively. To install just one, add `--skill <skill-name>`.

When using a different agent swap `--agent claude-code` for `codex`, `cursor`, `github-copilot`, etc. — run `npx skills add --help` for the full list.

## Skills

| Skill | When it fires |
|---|---|
| [`map-inspect-packages`](skills/map-inspect-packages/SKILL.md) | Starting work in the Inspect AI ecosystem. Picks the right package for a given task and points at its docs. |
| [`reading-logs`](skills/reading-logs/SKILL.md) | Reading, inspecting, or processing Inspect AI eval log files (`.eval` or `.json`). Covers the `inspect_ai.log` API and memory-safe patterns. |

Run `npx skills update` periodically to pull the latest.
