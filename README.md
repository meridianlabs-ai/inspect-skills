# Inspect Skills

Coding agent skills for Inspect AI and its ecosystem (`inspect_ai`, `inspect_evals`, `inspect_flow`, `inspect_scout`, `inspect_viz`, `inspect_swe`, `inspect_harbor`, sandboxes).

## Install

### Claude Code (recommended)

```
/plugin marketplace add meridianlabs-ai/inspect-skills
/plugin install inspect-skills@meridian
```

#### Auto-update (recommended)

Third-party marketplaces are manual-update by default. To get our changes automatically (every push to `main` lands in your next Claude Code session), toggle auto-update on for the `meridian` marketplace from `/plugin` > Marketplaces, or add to your `~/.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "meridian": { "autoUpdate": true }
  }
}
```

To update manually instead: `/plugin marketplace update meridian` then `/reload-plugins`.

### Other agents (Codex, Cursor, GitHub Copilot, etc.)

```bash
npx skills add meridianlabs-ai/inspect-skills --agent <agent> -g -y
```

`-y` installs every skill non-interactively; add `--skill <skill-name>` to install just one. Updates: `npx skills update`. Run `npx skills add --help` for the full list of supported agents.

## Skills

| Skill | When it fires |
|---|---|
| [`map-inspect-packages`](skills/map-inspect-packages/SKILL.md) | Starting work in the Inspect AI ecosystem. Picks the right package for a given task and points at its docs. |
| [`reading-logs`](skills/reading-logs/SKILL.md) | Reading, inspecting, or processing Inspect AI eval log files (`.eval` or `.json`). Covers the `inspect_ai.log` API and memory-safe patterns. |
| [`babysitting-evals`](skills/babysitting-evals/SKILL.md) | Monitoring and diagnosing running Inspect AI evals via `inspect ctl` (the read-only control-channel CLI). Covers stall diagnosis, error triage, launch-and-watch workflows, and graceful stops. |
