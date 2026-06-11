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

### Codex

```bash
codex plugin marketplace add meridianlabs-ai/inspect-skills
codex plugin add inspect-skills@meridian
```

To update: `codex plugin marketplace upgrade meridian` (Codex has no auto-update equivalent; updates are manual).

### Other agents (Cursor, GitHub Copilot, etc.)

```bash
npx skills add meridianlabs-ai/inspect-skills --agent <agent> -g -y
```

`-y` installs every skill non-interactively; add `--skill <skill-name>` to install just one. Updates: `npx skills update`. Run `npx skills add --help` for the full list of supported agents.

## Skills

| Skill | When it fires |
|---|---|
| [`map-inspect-packages`](plugins/inspect-skills/skills/map-inspect-packages/SKILL.md) | Starting work in the Inspect AI ecosystem. Picks the right package for a given task and points at its docs. |
| [`reading-logs`](plugins/inspect-skills/skills/reading-logs/SKILL.md) | Reading, inspecting, or processing Inspect AI eval log files (`.eval` or `.json`). Covers the `inspect_ai.log` API and memory-safe patterns. |
| [`babysitting-evals`](plugins/inspect-skills/skills/babysitting-evals/SKILL.md) | Monitoring and diagnosing running Inspect AI evals via `inspect ctl` (the read-only control-channel CLI). Covers stall diagnosis, error triage, launch-and-watch workflows, and graceful stops. |

## Contributing

### Commit conventions

PR titles must follow [Conventional Commits](https://www.conventionalcommits.org/) (enforced via the `pr-title-lint` workflow). The repo squashes PRs on merge, so the PR title becomes the main-branch commit.

Common prefixes and what they do:

| Prefix | Effect on releases | Visible in CHANGELOG? |
|---|---|---|
| `feat:` | minor version bump on next Codex release | yes (Features) |
| `fix:` | patch version bump on next Codex release | yes (Bug Fixes) |
| `perf:` | patch | yes (Performance Improvements) |
| `revert:` | patch | yes (Reverts) |
| `docs:` | no release on its own; piggybacks the next `feat:`/`fix:` | yes (Documentation) |
| `refactor:` / `chore:` / `ci:` / `build:` / `test:` / `style:` | no release on its own | no |

**Important: SKILL.md content changes should use `fix:`, not `docs:`.** The skills ARE the user-facing artifact, so corrections and refinements are fixes to it. `docs:` is reserved for repo-level documentation that isn't shipped to users (README, TODOS, this Contributing section).

### Releases

Releases use [release-please](https://github.com/googleapis/release-please-action) on every push to `main`. The flow:

1. You merge a feature PR with a Conventional Commit title.
2. release-please opens (or updates) a "Release PR" that bumps the version and writes a CHANGELOG entry.
3. You merge the Release PR when you want to ship. A Git tag and GitHub release are created.

### Why Claude Code and Codex have different release behaviors

The two platforms have different update models, so we ship to them differently:

| | Claude Code | Codex |
|---|---|---|
| Update trigger | Auto-update at session start (per the SHA of the marketplace HEAD) | Manual `codex plugin marketplace upgrade meridian` |
| Version key | Commit SHA (no version field) | `plugin.json#version` (release-please-bumped) |
| When users see changes | On the next session after every push to `main` | After the Release PR is merged (bump invalidates Codex's version-keyed cache) |
| Affected files | `.claude-plugin/marketplace.json` | `plugins/inspect-skills/.codex-plugin/plugin.json` |

This is by design: Claude Code's auto-update supports fast iteration; Codex's version-keyed cache requires explicit version bumps ([openai/codex#21138](https://github.com/openai/codex/issues/21138)). Merging a feature PR to `main` reaches Claude Code users immediately; Codex users see the change after the Release PR is merged.
