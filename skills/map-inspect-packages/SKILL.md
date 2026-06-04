---
name: map-inspect-packages
description: Use whenever the user is working with Inspect AI or any of its ecosystem packages (Evals, Flow, Scout, Viz, SWE, Harbor, Sandboxes). Maps concerns to packages and points at each package's docs before calling its API.
---

# Inspect AI Ecosystem

Inspect AI is the UK AI Security Institute's open-source Python framework for LLM evaluations. The ecosystem is split across several packages, each owning a distinct concern. Pick the right one before writing code; fetch the package's `llms.txt` (or docs root) before calling its API or writing more than a few lines against it.

**Defer to a more specific skill if one exists.** If another installed skill's description more specifically matches the request (e.g. one dedicated to log reading, log mutation, eval writing, etc.), use that one. This skill covers ecosystem routing only.

| Package | Owns | Docs |
|---|---|---|
| **Inspect AI** | Core eval framework: `Task` / `Solver` / `Scorer` / datasets / models and providers / agents / tools / sandbox API / log and analysis APIs (`inspect_ai.log`, `inspect_ai.analysis`) / eval runners (`eval()`, `eval_set()`). | https://inspect.aisi.org.uk/llms.txt |
| **Inspect Evals** | Community catalog of 130+ pre-built benchmark evals (GAIA, SWE-Bench, Cybench, MMLU, GPQA, …). Use these before writing your own. | https://ukgovernmentbeis.github.io/inspect_evals/index.html |
| **Inspect Flow** | Declarative workflow orchestration: run many tasks × models × params at scale, with sweeps, defaults, and post-eval steps (`FlowSpec`, `FlowTask`). | https://meridianlabs-ai.github.io/inspect_flow/llms.txt |
| **Inspect Scout** | In-depth analysis of AI agent transcripts via LLM, grep/pattern, or multi-agent scanners. Detects issues like refusals, misconfiguration, or evaluation awareness. Imports natively from Inspect logs, plus Arize Phoenix, LangSmith, Logfire, MLFlow, W&B Weave, Claude Code sessions, and arbitrary Arrow/Parquet/custom Python sources. | https://meridianlabs-ai.github.io/inspect_scout/llms.txt |
| **Inspect Viz** | Data visualization for Inspect log dataframes: bar charts, line and scatter plots, scorer & sample heatmaps, radar plots, with interactive filtering and tables. | https://meridianlabs-ai.github.io/inspect_viz/llms.txt |
| **Inspect SWE** | Software-engineering agent scaffolds (Claude Code, Codex CLI) usable as Inspect solvers. | https://meridianlabs-ai.github.io/inspect_swe/llms.txt |
| **Sandboxes** | Isolated environments for sample execution. Docker is built into Inspect AI for local execution. Beyond that, several external sandbox packages exist: managed cloud (e.g. Inspect Sandboxes with Daytona/Modal) and self-hosted (K8s, Proxmox, EC2, …). | [Inspect Sandboxes](https://meridianlabs-ai.github.io/inspect_sandboxes/llms.txt) · [k8s](https://k8s-sandbox.aisi.org.uk/) · [proxmox](https://github.com/UKGovernmentBEIS/inspect_proxmox_sandbox) · [ec2](https://github.com/UKGovernmentBEIS/inspect_ec2_sandbox) |
| **Inspect Harbor** | Bridge to [Harbor](https://harborframework.com/) containerized agent benchmarks (e.g. Terminal Bench) as Inspect tasks. | https://meridianlabs-ai.github.io/inspect_harbor/llms.txt |

The table above is curated for the most-used packages. For the comprehensive ecosystem catalog (25+ extensions including community projects from METR, Redwood, Transluce, Vector Institute, and more), fetch [Inspect Extensions](https://inspect.aisi.org.uk/extensions/index.html.md).

## Picking the right package

- *"Write/run an eval against a model"* → **Inspect AI**. First check **Inspect Evals**, the [**Inspect AI evals catalog**](https://inspect.aisi.org.uk/evals/index.html.md) (cross-ecosystem index across 12 categories), and [**Inspect Harbor**'s registry](https://meridianlabs-ai.github.io/inspect_harbor/registry.html) to see if the benchmark already exists.
- *"Simple sweep across models or tasks (one-off)"* → **Inspect AI**'s `eval_set()` (built-in, supports multi-model and multi-task runs directly).
- *"Reusable / declarative orchestration: config-driven runs, post-eval workflows, or re-running the same setup later"* → **Inspect Flow** (rather than a hand-rolled Python wrapper around `eval_set()`).
- *"Identify patterns across many samples, or analyze long agent trajectories"* → **Inspect Scout**.
- *"Plot or dashboard eval results"* → **Inspect Viz**.
- *"Evaluate a coding agent"* → **Inspect SWE** for the agent, **Inspect Evals** (SWE-Bench, etc.) or **Inspect Harbor** for the benchmark.
- *"Sample needs an isolated environment"* → **Inspect AI** sandbox API. Default to the built-in Docker sandbox for development and small/test runs; reach for an external sandbox package (managed cloud or self-hosted K8s/Proxmox/EC2) for large-scale runs, resource-intensive tasks, or GPU needs.
- *"Read or inspect a single eval log or a handful of samples"* → **Inspect AI** (`inspect_ai.log` for one log; `inspect_ai.analysis` for cross-log dataframes). Use this rather than Scout when you're looking at one log or a small set.
- *"Add a custom scorer, solver, tool, or dataset"* → **Inspect AI** core.

## Before calling the API

**ALWAYS fetch and consult the relevant `llms.txt` (or docs root) before answering any question or writing any code about these packages**, even when you believe you know the API. The descriptions above are routing hints, not specs; the docs are the source of truth and change frequently. Prior-knowledge answers drift quickly and may reference renamed, moved, or removed APIs.

**Keep packages aligned with the docs.** Check the user's installed version (`pip show <package>`) against the latest on PyPI. If it's older, propose upgrading (`pip install -U <package>`) so the features in the docs are actually available at runtime. If the user can't upgrade (pinned deps, monorepo constraints), flag the version gap and consult the installed version's release notes for any drift.

**Tip: `inspect.aisi.org.uk` markdown convention.** Any docs page on `inspect.aisi.org.uk` has a markdown variant: append `.html.md` to the URL (e.g. `https://inspect.aisi.org.uk/agents.html.md`). The HTML versions are JS-rendered and may return empty content to fetch tools; use the `.html.md` variant for reliable agent-readable content.

---

Last reviewed: 2026-06-04 against inspect_ai v0.3.235