# Inspect Skills

Skills that help coding agents work with [Inspect AI](https://inspect.aisi.org.uk/) and its ecosystem: picking the right package, reading and analyzing eval logs, and monitoring running evals.

## What it does

The plugin bundles four skills. Each one loads automatically when a request matches it; you don't invoke them by name.

| Skill | Use it for |
|---|---|
| `map-inspect-packages` | Starting work in the Inspect ecosystem (Inspect AI, Evals, Flow, Scout, Viz, SWE, Harbor, sandboxes). Picks the package for the task and points at its docs. |
| `reading-logs` | Reading `.eval` / `.json` log files with the `inspect_ai.log` API, memory-safe patterns for large logs, crash recovery, and trace logs. |
| `analyzing-logs` | Questions about what happened in an eval: single-log reads, cross-log dataframes (`inspect_ai.analysis`), or transcript pattern detection (Inspect Scout). |
| `babysitting-evals` | Watching a running eval with `inspect ctl`: stall and error diagnosis, cancelling samples or tasks, pausing, and retuning concurrency or timeouts mid-run. |

## How to use it

Install from the Meridian marketplace:

```
/plugin marketplace add meridianlabs-ai/inspect-skills
/plugin install inspect-skills@meridian
```

Then ask about your evals in plain language, for example "what went wrong in `logs/run.eval`?", "compare scores across these runs", or "watch this eval and tell me if it stalls".

The skills call the `inspect` CLI and the `inspect_ai` Python package in your environment, so install Inspect AI (`pip install inspect-ai`) in the project you're working in.

## Optional Python REPL server

The plugin also registers a local MCP server, `py-repl` ([`posit-dev/mcp-repl`](https://github.com/posit-dev/mcp-repl), pinned to `posit-mcp-repl==0.3.0`). `analyzing-logs` uses it to keep eval-log dataframes in memory across follow-up questions. It is only needed for that workflow; without it the skill falls back to stateless reads.

- **Setup:** install [`uv`](https://docs.astral.sh/uv/getting-started/installation/); the server starts on demand through `uvx`.
- **Sandbox:** the REPL runs Python in an OS-level sandbox that can write only inside your workspace and reach only `pypi.org` and `files.pythonhosted.org` (for installing `inspect-ai`, `pandas`, and `pyarrow` on first use).
- **Availability:** it's a local (stdio) server, so it works in Claude Code and Cowork but not in claude.ai on the web.

The plugin requires no API keys or credentials.

## More

See the [repository README](https://github.com/meridianlabs-ai/inspect-skills#readme) for Codex and other agents, auto-update settings, and contributing.
