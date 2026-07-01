---
name: analyzing-logs
description: >-
  Use whenever the user wants to analyze or understand what happened in an
  Inspect AI eval, sample, or set of logs. Routes to the right tool
  (`inspect_ai.log` for single-log work, `inspect_ai.analysis` for cross-log
  dataframes, Inspect Scout for transcript pattern detection) and covers the
  `inspect_ai.analysis` surface for ad-hoc analysis. Triggers on questions
  like "what happened in this eval/sample", "how did model X compare to Y",
  "show me outliers across these runs", "did any sample do X", or any
  follow-up where the user is analyzing logs (not just reading them).
---

# Analyzing Inspect eval logs

Use this skill when the user asks **questions about what happened** in one or more eval logs. The first job is to pick the right tool for the question; the second is to apply it.

## Pick the right tool

| Question shape | Tool | Skill |
|---|---|---|
| About **one** log header, one sample's content, one sample's error history | `inspect_ai.log` | `reading-logs` skill |
| About **many** samples or logs at once: aggregates, score distributions, comparisons, outliers, dataframes | `inspect_ai.analysis` | this skill, below |
| **Pattern detection** inside transcripts: "did any sample refuse / reward-hack / repeat / get stuck", "find samples where X happened in the messages" | **Inspect Scout** | [Inspect Scout docs](https://meridianlabs-ai.github.io/inspect_scout/llms.txt) |

The boundary cues:

- **Single log or sample → `reading-logs`.** A question answerable by reading one log's header or one sample's `.messages` belongs there, not here. Even if the question is "about transcript content" for one specific sample, it's still a single-sample read. **When you drop down to single-sample work mid-analysis, invoke the `reading-logs` skill explicitly** — its decision tree covers the right `read_eval_log_sample` / `read_eval_log_samples` patterns plus the `all_samples_required=False` caveat for non-success logs.
- **Cross-sample numerical aggregates → this skill (`inspect_ai.analysis`).** Score distributions, model comparisons, token-usage rollups, outliers, anything that wants a table with one row per sample or per run.
- **Pattern mining inside transcripts → Scout.** "Did any sample do X" / "find samples where Y" questions, where the answer requires scanning the *content* of many transcripts.

## Cross-log / cross-sample analysis: `inspect_ai.analysis`

When the question is "how do these samples or runs compare?", reach for `inspect_ai.analysis`. It builds **pandas dataframes** at four granularities; pick the cheapest one that answers the question:

| Builder | Output | Use when |
|---|---|---|
| `evals_df(logs)` | 1 row per log file | per-run rollups: which model scored highest, how long did each run take |
| `samples_df(logs)` | 1 row per sample | per-sample analysis across runs: score distributions, outliers, comparisons |
| `messages_df(logs)` | 1 row per message | message-content slicing: filter by role/function, count tool calls |
| `events_df(logs)` | 1 row per event | event-level timing or transcript reconstruction |

```python
from inspect_ai.analysis import samples_df, EvalModel, SampleSummary, SampleScores
df = samples_df("logs/", columns=EvalModel + SampleSummary + SampleScores)
```

**Composable columns.** Pick the granularity (one of the four `*_df` builders) and the columns you need from the pre-built groups (composed via `+`). Pre-built groups cover most needs:

- Eval-level: `EvalInfo`, `EvalTask`, `EvalModel`, `EvalDataset`, `EvalConfiguration`, `EvalResults`, `EvalScores`
- Sample-level: `SampleSummary`, `SampleScores`, `SampleMessages`
- Message-level: `MessageContent`, `MessageToolCalls`
- Event-level: `EventInfo`, `EventTiming`, `ModelEventColumns`, `ToolEventColumns`

Custom columns inherit from `EvalColumn` / `SampleColumn` / `MessageColumn` / `EventColumn`.

**Common args.** `parallel=True` for full-content reads (capped at 8 workers; not available on `evals_df`). `strict=False` returns `(df, errors)` so partial failures don't raise; always unpack the tuple: `df, errors = samples_df(..., strict=False)`.

**`prepare(df, [...])`** chains post-build operations: `model_info` (add org, display name, release date), `task_info` (task display names), `log_viewer` (local paths to URLs), `frontier` (mark top performers per task), `score_to_float` (score column conversion). Reach for it when enriching dataframes for plots or leaderboards.

**Three traps to know about up front:**

- **Score columns: single-scorer vs multi-scorer.** `samples_df` explodes scores into one column per scorer (`score_<scorer-name>`). For a one-scorer eval, group by that single column and aggregate. For multi-scorer / cross-scorer comparisons, prefer **`evals_df` with `EvalScores`** (gives you `score_headline_value` per log) and accept that you're averaging across scorers. Values can be strings (`'C'`/`'I'`), numbers, or nested dicts depending on the scorer; use `prepare(df, [score_to_float("score_headline_value")])` for eval headline scores, or pass the concrete sample score column(s) such as `score_<scorer-name>` when normalizing `samples_df`.
- **pyarrow dtypes bite scalar comparisons.** `samples_df` returns columns with pyarrow-backed dtypes (`double[pyarrow]`, `large_string[pyarrow]`). Plain `df[col].isna()` works, but scalar `==` on `<NA>` raises `TypeError: boolean value of NA is ambiguous`. Use `pd.to_numeric(df[col], errors='coerce')` or `df[col].fillna(...)` before comparing.
- **Status field canonical values.** `EvalLog.status ∈ {success, error, cancelled, started}`. `started` means the run crashed mid-execution (see `reading-logs` for `recoverable_eval_logs` recovery). Filter on these explicitly rather than guessing.

**ALWAYS fetch and read https://inspect.aisi.org.uk/dataframe.html.md before doing any non-trivial analysis work.** The column system has more depth than this section covers, and the docs are the source of truth.

## Transcript pattern detection: Inspect Scout

For questions like "did any sample reward-hack", "find samples where the agent repeated the same tool call", "which transcripts show refusals": that's **Inspect Scout** territory. Don't try to express these as `messages_df` filter expressions; Scout's scanners are purpose-built for it and the result is more reliable. Point the user at https://meridianlabs-ai.github.io/inspect_scout/llms.txt for the surface.

## Reading the right log dir

Most analysis starts with a directory of logs. Default lookups:

- The user's working `logs/` directory if they're inside an Inspect project.
- `INSPECT_LOG_DIR` if set.
- The `log_location` from `ctl tasks --json` if the user is asking about a still-running eval (see `babysitting-evals`).

If ambiguous, ask. Don't guess.

**Multiple logdirs**: the dataframe builders take `LogPaths | EvalLog | Sequence[EvalLog]`, so you can pass a list of paths to analyze several logdirs in one call, e.g. `samples_df(["runs/2026-06/", "runs/2026-05/"])`.

## Keeping logs in memory across questions

When the user is going to ask several follow-up questions about the same log (or a set of logs), don't re-read on every turn. Set up **persistent state** via a Python REPL MCP, i.e. a tool that keeps a Python interpreter alive across calls so variables you define in one call are still there in the next.

**When to set this up:**

- The user explicitly asks for an analysis session, or signals follow-ups are coming ("walk me through this", "now show me X about the same log").
- The log is large enough that re-reading hurts: roughly, multi-GB on disk, or hundreds of samples you'd otherwise stream on each turn.
- You're using `samples_df` (or any full-content read); the deserialized dataframe is expensive to rebuild from scratch every turn.

For a one-shot question on a small log, skip this; reload is cheaper than setup.

**How to do it.** This plugin bundles a persistent Python REPL MCP server ([`posit-dev/mcp-repl`](https://github.com/posit-dev/mcp-repl)). The server name depends on the agent: on Claude Code it's `plugin:inspect-skills:py-repl` (namespaced because plugin-bundled MCPs use a `plugin:<plugin-name>:<server-name>` prefix); on Codex it's registered flat as `py-repl` (no plugin prefix, as shown by `codex mcp list`) and the tools are invoked by their bare names. Two tools:

- `repl`, args: `input` (the Python source to run, as a string) and optional `timeout_ms`. State persists across calls. Plots from `matplotlib` etc. are returned as inline images when the client model is vision-capable; otherwise as file paths. Smart-echo suppresses redundant stdout. The session runs in an OS-level sandbox at the `workspace-write` policy: reads broadly, writes only inside the workspace, network restricted to allowlisted PyPI domains (`pypi.org`, `files.pythonhosted.org`) so the dep-bootstrap can `pip install` but the REPL can't otherwise reach the network.
- `repl_reset`, no args. Restarts the backend session and clears all in-memory state. **Don't call this mid-session** — it wipes the dataframes you've been building up. Reach for it only if the user explicitly wants a clean slate, or if the worker has wedged and you need a fresh start.

**Always end multi-line `repl` inputs with `\n\n`.** Posit's REPL runs in line-mode and waits for a trailing blank line to evaluate indented blocks (`def`, `for`, `if`, `class`, etc.) — without it the REPL stays in continuation mode and your *next* `repl` call gets fed in as more lines of the unterminated block. Always append `\n\n` to any `input` containing indented code. Single-statement inputs (`x = 1`, `print(x)`) don't need it but it's harmless to include. If you see "continuation"-style behavior or the REPL seems to ignore your input, send a single `\n\n` to flush the pending block — don't reach for `repl_reset` since that wipes state.

**Or wrap multi-line code in `exec(r'''...''')` to sidestep line-mode entirely.** Triple-quoted raw string + `exec` makes the whole block a single Python statement from the REPL's POV, so there's no continuation to terminate and no `\n\n` to remember. Slight visual noise, but it eliminates the class of bug. Both patterns are fine — pick whichever reads better per call:

```python
exec(r'''
import pandas as pd
for col in df.columns:
    print(col, df[col].dtype)
''')
```

**Bootstrap dependencies on the first call.** `posit-mcp-repl` uses whatever Python interpreter it discovers (nearest `.venv` walking up from cwd, then `python3` on PATH). It does not manage its own package environment. So your first `repl` call should ensure `inspect-ai`, `pandas`, and `pyarrow` are importable, and `pip install` them if they're not:

```python
import subprocess, sys
for pkg, mod in [("inspect-ai==0.3.241", "inspect_ai"),
                 ("pandas==2.3.3", "pandas"),
                 ("pyarrow==24.0.0", "pyarrow")]:
    try:
        __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pkg])
```

When sending this to `repl`, **the `input` string must end with `\n\n`** — it contains an indented `for` block, and Posit's line-mode REPL needs the trailing blank line to evaluate. (Same rule applies to every multi-line block you send.)

If `inspect_ai` is already on the user's Python, the loop is a no-op (each `__import__` succeeds, no install). Otherwise it installs the three pinned versions into whatever environment Posit discovered. This only runs once per session — subsequent `repl` calls reuse the loaded modules.

- **Claude Code**: the MCP starts automatically when the plugin is enabled. Use it directly.
- **Codex**: the MCP is bundled but may be either disabled in config or lazy-loaded rather than listed up front. Try the `tool_search` discovery step below first; if discovery still doesn't expose the tool, point the user at the README for the enable step.
- **Other agents installed via `npx skills add`** (Cursor, GitHub Copilot, Windsurf, Cline): the MCP isn't auto-registered. Point the user at the plugin README's per-agent JSON snippets (the one they paste depends on the agent — VS Code Copilot's schema is different from the rest). They restart their agent to pick it up.

If the tool still isn't visible after discovery, fall back to the stateless pattern below; don't block the analysis on getting the MCP set up. Common reasons the tool won't be visible:

- The user is on an agent we don't have a recipe for, or they prefer a different REPL MCP, or the bundled MCP just isn't installed in their config.
- **You're running as a subagent in Claude Code with a restricted `tools:` allowlist.** The bundled REPL reaches subagents only through the deferred-tool channel, loaded on demand via `ToolSearch`. Subagents with a wildcard (`tools: *`) or exclusion-style `tools:` declaration inherit it fine. But an agent defined with an *enumerated-include* `tools:` list that omits `ToolSearch` gets no deferred-tools list and no `ToolSearch` at all, so there's no channel to load the REPL schema and the MCP is unreachable. If that's you, either add `ToolSearch` (or use `tools: *`) to the agent definition, or fall back to the stateless reads below. If the parent needs persistent state, it can also just do the analysis itself rather than delegating to a tools-restricted subagent.

The pattern with the MCP available (after the dep-bootstrap above):

```python
# First call: load once
from inspect_ai.log import read_eval_log, read_eval_log_samples
header = read_eval_log("logs/run.eval", header_only=True)
# all_samples_required=False so partial / errored / cancelled logs don't raise.
samples = list(read_eval_log_samples("logs/run.eval", all_samples_required=False))

# Subsequent calls: just reference `header` and `samples`. State persists.
[s for s in samples if s.error is not None]
```

## Capturing the analysis to a runnable file (opt-in)

Exploratory analysis can leave the user with no durable artifact when the session ends. Offer an opt-in record they can re-run from scratch and keep.

For any **multi-turn or exploratory log-analysis session**, surface the capture option before or alongside the first substantive analysis step. This applies whether you use a persistent REPL MCP or fall back to stateless shell/Python commands. Do not skip this just because the REPL tool is unavailable.

**Ask via your agent's structured-question tool** (e.g., `AskUserQuestion` in Claude Code) when available. Don't bury the offer in a planning message, and don't pair the question with your own decision in the same message — phrasing like "I'll leave it off for now and continue" makes the user think the choice is already made and they often won't react. State the question on its own; if your agent can't pause for a reply, begin the analysis without capture (capture is off by default until the user explicitly opts in — they can say yes any later turn). If your agent doesn't expose a structured-question tool, ask a standalone, clearly-formatted question instead.

The question:

> "Want me to capture this analysis to a file you can keep and re-run? I can write a **Python script** (`.py`, runs end-to-end with `python …`), a **Jupyter notebook** (`.ipynb`, opens in JupyterLab with inline output), or skip it."

Three options:
- **Python script (`.py`)** *(default)* — a cleaned-up, linear script named `inspect-analysis-<timestamp>.py` that runs top-to-bottom from a fresh interpreter. Imports at the top, one commented section per keeper step, plots as `plt.savefig(...)`. Diffs cleanly in git, needs no Jupyter, and re-running it regenerates every result. Prefer this unless the user asks for a notebook.
- **Jupyter notebook (`.ipynb`)** — cells with captured stdout and inline plots, for users who live in JupyterLab.
- **No file** — skip capture; any persistent REPL state still works for follow-up questions during this session.

Whichever format they pick, two principles hold for both:

- **Keepers only.** Skip throwaway exploration (`print(dir(thing))` to figure out an API, error tracebacks you worked around, type-probe calls). Keep the steps that move the user's question forward.
- **Don't claim to have written something without actually running the tool call.** The most common failure mode is writing "captured that step" or "appended this as a cell" in your message *without* the underlying file-write / `append` call. If you state something landed, the matching tool call must appear in the same turn. If you're not sure whether it ran, read the file back before saying "done."

### If they pick a notebook (`.ipynb`)

**Find the helper script** (shipped inside this skill's directory). If multiple copies exist across plugin caches, pick the newest by mtime:

```bash
APPEND=$(find ~/.claude/plugins ~/.codex/plugins ~/.agents/skills -name append_to_notebook.py 2>/dev/null \
  | python3 -c "import sys, os; ps=[l.strip() for l in sys.stdin if l.strip()]; print(max(ps, key=os.path.getmtime, default=''))")
```

This searches all three install layouts (Claude Code plugin cache, Codex plugin cache, `npx skills add` under `~/.agents/skills/analyzing-logs/scripts/`) and picks the most recently updated copy so stale caches don't shadow the current version. If `$APPEND` is empty, tell the user and skip the capture; don't try to reconstruct the script inline.

**Create the notebook** (auto-named, prints the path):

```bash
NB=$(python3 "$APPEND" init)
```

**Append at natural pause points, in batches.** End of a logical step, end of a turn, before you summarise a finding — that's when you append. One Bash with several `cat <<EOF` + `append` invocations is cleaner than a separate Bash after every `repl` call, and it lets you pick keepers with hindsight (you'll know which exploratory blocks led somewhere useful).

**Verify cells actually landed.** Per the keepers-only / don't-claim-without-running rule above, the `append` here is the tool call that must appear in the same turn as any "appended this as a cell" claim. If you're not sure whether it ran, list the notebook cells (read the `.ipynb` with your file-read tool, or `python3 -c 'import json; print(len(json.load(open("'"$NB"'"))["cells"]))'`) before saying "done."

Use `mktemp -d` for the temp files so they're per-session (no name collisions across analysis sessions on the same machine, and not world-readable in shared `/tmp`):

```bash
TMP=$(mktemp -d)
cat > "$TMP/c1.py" <<'CODE'
<keeper code 1>
CODE
cat > "$TMP/c1.out" <<'OUT'
<captured stdout 1>
OUT
python3 "$APPEND" append "$NB" --code-file "$TMP/c1.py" --output-file "$TMP/c1.out"

cat > "$TMP/c2.py" <<'CODE'
<keeper code 2>
CODE
# ... etc

rm -rf "$TMP"   # clean up at end of batch
```

**Capture plots inline.** When a `repl` call produces a plot, save the figure to a PNG inside your `repl` code before calling `plt.show()`, then pass it to `append` via `--image-file`. Two small habits matter:

- **Suppress the noisy return value** with `_ =` or a trailing `;`. `plt.hist(...)` returns a `(counts, bins, patches)` tuple that can trip the oversized-output handler. We already configure `--oversized-output files` so it spills to disk instead of getting stuck in a pager, but suppressing is still cleaner.
- **Save to disk as the source of truth.** The inline render returned by Posit can come up empty on the very first `matplotlib` call in a session (font cache build races with the capture). `plt.savefig` always works, so write the file first and rely on `--image-file` for the captured notebook output. If you need to verify the plot before continuing, read the saved PNG via your file-read tool.

```python
import matplotlib.pyplot as plt
_ = plt.hist(tokens, bins=50)
plt.title("Token distribution")
plt.savefig("/tmp/cell-plot.png", dpi=80, bbox_inches="tight")
plt.show()  # also renders inline for vision-capable clients (best-effort)
```

then on the host:

```bash
python3 "$APPEND" append "$NB" --code-file "$TMP/cN.py" --output-file "$TMP/cN.out" --image-file /tmp/cell-plot.png
```

The PNG is embedded as a `display_data` output so the plot renders the moment the user opens the notebook in JupyterLab — they don't need to Run All to see it. The code cell still runs cleanly from a fresh kernel because `plt.savefig` regenerates the image. Use a fresh `--image-file` path per cell (e.g., `$TMP/cN.png`) if you're appending several plot cells in one batch.

**Cells must be self-contained.** The REPL state is for *exploration* — variables built across many back-and-forth calls. The notebook is the *curated record* — someone should be able to Run All from a fresh kernel and reproduce. So when appending a cell, inline the imports it needs, the variables it references, and the paths it reads. If a piece of state was built across five exploratory blocks in the REPL, collapse it into one self-contained cell in the notebook.

**What is and isn't captured.** Code, stdout, and saved PNG plots are captured. For plots, save the figure and pass the PNG via `--image-file`; the helper embeds it as `display_data` so it renders when the notebook opens. Not captured today: rich `display(df)` HTML or unsaved inline renders returned only by the REPL.

---

Last reviewed: 2026-06-26 against inspect_ai v0.3.241
