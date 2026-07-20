# Inspect Skills

Coding agent skills for [Inspect AI](https://inspect.aisi.org.uk/) and its ecosystem (`inspect_ai`, `inspect_evals`, `inspect_flow`, `inspect_scout`, `inspect_viz`, `inspect_swe`, `inspect_harbor`, sandboxes).

## What's in this plugin

This is a single plugin that bundles four skills. Installing it gets you all four; disable individual ones in your agent's settings if you don't want some.

| Skill | When it fires |
|---|---|
| [`map-inspect-packages`](plugins/inspect-skills/skills/map-inspect-packages/SKILL.md) | Starting work in the Inspect AI ecosystem. Picks the right package for a given task and points at its docs. |
| [`reading-logs`](plugins/inspect-skills/skills/reading-logs/SKILL.md) | Reading, inspecting, or processing Inspect AI eval log files (`.eval` or `.json`). Covers the `inspect_ai.log` API and memory-safe patterns. |
| [`analyzing-logs`](plugins/inspect-skills/skills/analyzing-logs/SKILL.md) | Analyzing what happened in evals or samples. Routes between `inspect_ai.log` (single log), `inspect_ai.analysis` (cross-log dataframes), and Inspect Scout (transcript patterns). |
| [`babysitting-evals`](plugins/inspect-skills/skills/babysitting-evals/SKILL.md) | Monitoring and diagnosing running Inspect AI evals via `inspect ctl` (the read-only control-channel CLI). Covers stall diagnosis, error triage, launch-and-watch workflows, and graceful stops. |

The plugin also ships an optional Python REPL MCP server used by `analyzing-logs` for keeping eval-log dataframes in memory across follow-up questions. Skip the MCP setup steps below if you don't need it; see [Bundled MCP server](#bundled-mcp-server) for what it does and when it helps.

## Install

### Claude Code (recommended)

```
/plugin marketplace add meridianlabs-ai/inspect-skills
/plugin install inspect-skills@meridian
```

This installs all four skills. The bundled MCP server is registered and starts on demand — no extra setup needed.

#### Auto-update (recommended)

Third-party marketplaces are manual-update by default. To get our changes automatically (every push to `main` lands in your next Claude Code session), copy-paste this into your `~/.claude/settings.json` (user-wide) or a repo's `.claude/settings.json` (shared: everyone who opens that repo gets the skills, without running the install commands):

```json
{
  "extraKnownMarketplaces": {
    "meridian": {
      "source": {
        "source": "github",
        "repo": "meridianlabs-ai/inspect-skills"
      },
      "autoUpdate": true
    }
  },
  "enabledPlugins": {
    "inspect-skills@meridian": true
  }
}
```

The snippet is self-contained: `enabledPlugins` is what actually installs and enables the plugin at session start, while `extraKnownMarketplaces` registers the marketplace and turns on auto-update. Registering the marketplace alone (in the UI or in settings) installs **nothing** by itself.

Alternatively, toggle auto-update on from `/plugin` > Marketplaces. To update manually instead: `/plugin marketplace update meridian` then `/reload-plugins`.

#### Optional: skip per-call permission prompts on the MCP

To allowlist the bundled MCP's tools and skip the permission prompt that fires on every tool call, add to `~/.claude/settings.json` (user-wide) or `.claude/settings.json` / `.claude/settings.local.json` (repo-local):

```json
{
  "permissions": {
    "allow": [
      "mcp__plugin_inspect-skills_py-repl__repl"
    ]
  }
}
```

### Codex

```bash
codex plugin marketplace add meridianlabs-ai/inspect-skills
codex plugin add inspect-skills@meridian
```

This installs all four skills.

**Only if you want to use the bundled MCP** (the cross-log REPL workflow in `analyzing-logs`), add to `~/.codex/config.toml`:

```toml
[plugins."inspect-skills@meridian"]
enabled = true

[plugins."inspect-skills@meridian".mcp_servers."py-repl"]
enabled = true
default_tools_approval_mode = "prompt"
```

The `mcpServers` field in `.codex-plugin/plugin.json` registers the server with the plugin; the TOML block above explicitly enables it and sets the default tool approval policy. Use `prompt` if you want Codex to ask before running REPL tools. Change it to `approve` only if you're comfortable auto-approving the bundled Python REPL MCP tools:

```toml
default_tools_approval_mode = "approve"
```

Restart Codex (or start a fresh `codex` session) after editing the TOML. Verify with `codex mcp list`; `py-repl` should appear with status `enabled`. Both interactive `codex` and non-interactive `codex exec` work; no bypass flags needed.

To update: `codex plugin marketplace upgrade meridian` (Codex has no auto-update equivalent; updates are manual).

### Cursor / GitHub Copilot / Windsurf / Cline

```bash
npx skills add meridianlabs-ai/inspect-skills --agent <agent> -g -y
```

This installs all four skills. `-y` runs non-interactively; add `--skill <skill-name>` to install just one. Updates: `npx skills update`. Run `npx skills add --help` for the full list of supported agents.

**Only if you want to use the bundled MCP** (the cross-log REPL workflow in `analyzing-logs`), paste this snippet into your agent's MCP config file:

```json
{
  "mcpServers": {
    "py-repl": {
      "command": "uvx",
      "args": ["--from", "posit-mcp-repl==0.3.0", "mcp-repl", "--interpreter", "python", "--sandbox", "workspace-write", "--add-allowed-domain", "pypi.org", "--add-allowed-domain", "files.pythonhosted.org", "--oversized-output", "files"]
    }
  }
}
```

Per-agent config file location:
- **Cursor** — `~/.cursor/mcp.json`
- **Windsurf** — `~/.codeium/windsurf/mcp_config.json`
- **Cline / other clients** — whatever config file the client reads (most use the `mcpServers` shape above)

**GitHub Copilot in VS Code** uses a different schema. Use this snippet instead, in `<workspace>/.vscode/mcp.json`:

```json
{
  "servers": {
    "py-repl": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "posit-mcp-repl==0.3.0", "mcp-repl", "--interpreter", "python", "--sandbox", "workspace-write", "--add-allowed-domain", "pypi.org", "--add-allowed-domain", "files.pythonhosted.org", "--oversized-output", "files"]
    }
  }
}
```

Restart your agent to pick up the new MCP server.

## Bundled MCP server

The plugin bundles [`posit-dev/mcp-repl`](https://github.com/posit-dev/mcp-repl), a persistent Python REPL MCP server. The `analyzing-logs` skill uses it to **keep eval-log dataframes in memory** across follow-up questions, so the agent doesn't re-read your `logs/` directory on every turn.

Worth setting up if you analyze many or large logs and ask several questions in a row; skip it otherwise — the skill falls back to stateless reads. The MCP runs arbitrary Python, so only enable it in environments where you're comfortable with that.

**Subagents and the bundled REPL.** Subagents spawned via the Task / Agent tool inherit the REPL through the deferred-tool channel, loaded on demand via `ToolSearch`. Wildcard (`tools: *`) and exclusion-style agent declarations inherit it fine. A custom agent pinned to an enumerated `tools:` allowlist must include `ToolSearch` (or use `tools: *`) to reach it — an enumerated list that omits `ToolSearch` gets no deferred-tools channel at all, which is the only path that loads the bundled MCP's schema.

### Prerequisites

[`uv`](https://docs.astral.sh/uv/) must be installed — the MCP launches via `uvx`, which is part of `uv`.

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Homebrew
brew install uv
```

See the [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/) for Windows, pip-based, and other install paths.

## Contributing

### Commit conventions

PR titles must follow [Conventional Commits](https://www.conventionalcommits.org/) (enforced via the `pr-title-lint` workflow). The repo squashes PRs on merge, so the PR title becomes the main-branch commit.

Common prefixes and what they do:

| Prefix | Effect on releases | Visible in CHANGELOG? |
|---|---|---|
| `feat:` | minor version bump on next Codex release | yes (Features) |
| `fix:` | patch version bump on next Codex release | yes (Bug Fixes) |
| `perf:` | patch version bump on next Codex release | yes (Performance Improvements) |
| `revert:` | patch version bump on next Codex release | yes (Reverts) |
| `docs:` | none on its own; piggybacks the next `feat:` / `fix:` | yes (Documentation) |
| `refactor:` / `chore:` / `ci:` / `test:` | none | no |

**Important: SKILL.md content changes should use `fix:`, not `docs:`.** The skills ARE the user-facing artifact, so corrections and refinements are fixes to it. `docs:` is reserved for repo-level documentation that isn't shipped to users.

### Releases

Claude Code and Codex have different release flows because their plugin update models differ:

- **Claude Code** uses the commit SHA as the implicit plugin version. If a user has enabled auto-update for the `meridian` marketplace, every push to `main` reaches them on their next session. By default, third-party marketplaces are manual-update, so users either toggle auto-update on (see [Install](#claude-code-recommended)) or run `/plugin marketplace update meridian` + `/reload-plugins` to pull changes.

- **Codex** caches each plugin by the `version` field in `.codex-plugin/plugin.json`. New commits to `main` do not reach Codex users via `codex plugin marketplace upgrade meridian` until the version bumps.

We use [release-please](https://github.com/googleapis/release-please-action) primarily to keep Codex users on the latest content. On every push to `main`, release-please opens (or updates) a "Release PR" that proposes a version bump and a CHANGELOG entry based on the Conventional Commits in the new commits. Merging the Release PR bumps the version in `plugins/inspect-skills/.codex-plugin/plugin.json`, after which Codex users can run `codex plugin marketplace upgrade meridian` to pull the new content.
