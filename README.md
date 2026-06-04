# Inspect Skills

Coding agent skills for Inspect AI and its ecosystem (`inspect_ai`, `inspect_evals`, `inspect_flow`, `inspect_scout`, `inspect_viz`, `inspect_swe`, `inspect_harbor`, sandboxes).

## Install

```bash
npx skills add meridianlabs-ai/inspect-skills
```

Installs all skills into your `~/.claude/skills/` so Claude Code (and other agents that read `SKILL.md`) can pick them up. To install just one:

```bash
npx skills add meridianlabs-ai/inspect-skills --skill <skill-name>
```

## Skills

| Skill | When it fires |
|---|---|
| [`map-inspect-packages`](skills/map-inspect-packages/SKILL.md) | Starting work in the Inspect AI ecosystem. Picks the right package for a given task and points at its docs. |

Run `npx skills update` periodically to pull the latest.
