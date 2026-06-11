---
name: reading-logs
description: Use whenever the user needs to read, inspect, or process Inspect AI eval log files (`.eval` or `.json`). Covers the Python API (`read_eval_log`, `read_eval_log_samples`, `read_eval_log_sample_summaries`, `list_eval_logs`), `header_only` mode, the critical anti-pattern of unzipping `.eval` files, and memory-safe patterns for large logs.
---

# Reading Inspect Eval Logs

**ALWAYS fetch and read https://inspect.aisi.org.uk/eval-logs.html.md before doing any work that involves reading Inspect log files.** The log-reading API is specific to Inspect AI and these docs are the source of truth. Do not skip this step, even if you think you know the API.

## The right API: `inspect_ai.log`

All log reading goes through `inspect_ai.log`. Pick the cheapest function that answers the question:

| Function | Use when |
|---|---|
| `list_eval_logs(path)` | You need to enumerate log files in a directory (recursive by default). |
| `read_eval_log(log_file, header_only=True)` | You only need task/model/status/config/aggregated results. Skips all sample data. **Fastest by far.** |
| `read_eval_log_sample_summaries(log_file)` | You need per-sample IDs and scores but not transcripts. Orders of magnitude faster than reading full samples. |
| `read_eval_log_sample(log_file, id=N)` | You need exactly one sample's full content. |
| `read_eval_log_samples(log_file)` | Generator over all samples. Use when you genuinely need full transcripts. Pass `all_samples_required=False` if the log status isn't `success` (cancelled or errored runs). |
| `read_eval_log(log_file)` | You really do need the whole log as one object. Last resort for big logs. |

```python
from inspect_ai.log import (
    list_eval_logs,
    read_eval_log,
    read_eval_log_sample,
    read_eval_log_samples,
    read_eval_log_sample_summaries,
)

# Enumerate logs in a directory
logs = list_eval_logs("logs/")

# Metadata only (cheapest)
header = read_eval_log("logs/run.eval", header_only=True)
print(header.eval.task, header.eval.model, header.status, header.results)

# Per-sample summaries (cheap, no transcripts)
for summary in read_eval_log_sample_summaries("logs/run.eval"):
    print(summary.id, summary.scores)

# Stream full samples (only when you actually need transcripts)
for sample in read_eval_log_samples("logs/run.eval"):
    process(sample)

# Stream even from a cancelled or errored log
for sample in read_eval_log_samples("logs/incomplete.eval", all_samples_required=False):
    process(sample)
```

## Never unzip `.eval` files

`.eval` files happen to be zip archives, but their internal layout is an implementation detail of Inspect, not a documented format. The Inspect docs are explicit:

> "The variability in underlying file format makes it especially important that you use the Python Log File API for reading and writing log files (as opposed to reading/writing JSON directly)."

**Do not do this** (a real anti-pattern agents fall into):

```python
# WRONG: reads internal layout that may change between versions
import zipfile, json, glob
for f in glob.glob("logs/**/*.eval", recursive=True):
    z = zipfile.ZipFile(f)
    n = len([x for x in z.namelist() if x.startswith("samples/") and x.endswith(".json")])
    epochs = json.loads(z.read("header.json"))["eval"]["config"].get("epochs")
    print(f, n, "epochs=", epochs)
```

Use `read_eval_log(..., header_only=True)` instead. The header gives you `eval.config.epochs`, `eval.task`, model, status, and more without touching zip internals. If the file format changes, `read_eval_log` stays correct; the zip-based code silently breaks or returns wrong data.

## Reason about resources before reading

Before reading log files, walk through:

1. **What do I actually need?** Task/model/status/config/results, per-sample scores, or full transcripts? The answer determines which API call.
2. **How many files?** One, a directory, thousands?
3. **How big are the files?** `ls -lh path/to/logs/`. The docs note that full logs can run to multiple GB.
4. **How much RAM does the machine have?** Check before reading anything large.

### Memory characteristics

- **Headers and sample summaries are small** (metadata only, KB-range per log). Looping with `header_only=True` or `read_eval_log_sample_summaries()` is safe regardless of file count. No memory reasoning needed in this case.
- **Full sample reads can be large.** The deserialized Python object is significantly bigger than the on-disk file (object overhead, message strings, tool calls). The docs caution that fully-loaded logs can be multiple GB.
- **Stream when you need full samples.** Use `read_eval_log_samples()` (a generator that yields one sample at a time) rather than `read_eval_log()` without `header_only`.
- **Long-running processes hold onto memory.** Python's allocator typically does not return freed heap memory to the OS, so iterating through many large logs in a single process makes RSS grow even after each log goes out of scope. If you have already read several full logs in the same process and memory matters, spawn a fresh subprocess per file (process exit fully releases memory). For a handful of logs this is overkill.
- **Parallel reads are fine when the total footprint fits.** Estimate from a single-file read first, then decide concurrency based on available RAM.

## Investigating errors

Three common error questions, with the right route for each:

- **"Why did the task fail?"** Start at the header for overall status, then walk summaries to find which samples errored:

  ```python
  header = read_eval_log("logs/run.eval", header_only=True)
  print(header.status)          # "success" / "error" / "cancelled"
  print(header.error)            # top-level error (if the eval itself crashed)

  for s in read_eval_log_sample_summaries("logs/run.eval"):
      if s.error is not None:
          print(s.id, s.error)   # samples that errored
  ```

  Drill into a specific failing sample with `read_eval_log_sample(path, id=...)` and inspect `sample.error` for traceback/message and `sample.messages` for the transcript leading up to it.

- **"What transient errors got retried during the run?"** Per-call retries (rate limits, network blips) are not preserved in the `.eval` log; only completed samples are stored. Use the trace logs instead (see "Runtime diagnostics: tracing" below). `inspect trace http --failed` is the most direct route.

- **"Why is this specific sample wrong (debugging)?"** Read just that sample and inspect its fields:

  ```python
  s = read_eval_log_sample("logs/run.eval", id=N)
  print(s.error)      # set if the sample errored out
  print(s.messages)   # full conversation
  print(s.scores)     # scorer outputs + explanations
  print(s.events)     # fine-grained events: tool calls, model calls, scoring
  ```

  The `events` field is the highest-resolution view of what actually happened step by step.

## Recovering a crashed eval log

If an eval process crashed mid-run, the `.eval` file may be missing samples that were already computed. Inspect maintains a per-event buffer DB on disk; completed samples are flushed to the `.eval` file periodically, so a crash before a flush leaves samples only in the buffer.

A log is recoverable when its `status` is `"started"` (the run crashed before completing) and the corresponding buffer DB still exists.

**Find recoverable logs in a directory** with `recoverable_eval_logs()` (returns `RecoverableEvalLog` entries whose `.log` attribute is an `EvalLogInfo` object, not a string; the path string is on `.log.name`):

```python
from inspect_ai.log import recoverable_eval_logs

for entry in recoverable_eval_logs("logs/"):
    print(entry.log.name, entry.flushed_samples, "/", entry.total_samples)
```

`RecoverableEvalLog` exposes `flushed_samples`, `completed_samples`, `in_progress_samples`, and `total_samples`.

**Recover one** with `recover_eval_log(log, output=None, overwrite=False, cleanup=True, no_events=False) -> EvalLog`. `log` must be a path string, so when chaining from `recoverable_eval_logs()` pass `entry.log.name`:

```python
from inspect_ai.log import recover_eval_log

# Direct path
recover_eval_log("logs/crashed-run.eval")
# default: writes logs/crashed-run-recovered.eval, removes buffer DB on success

# Chained from discovery
for entry in recoverable_eval_logs("logs/"):
    recover_eval_log(entry.log.name)
```

Useful options:

- `output=...` — write the recovered log to a specific path instead of `-recovered.eval` alongside the original.
- `overwrite=True` — replace the crashed log in-place.
- `no_events=True` — exclude per-sample event transcripts from the recovered log (much smaller / faster if you only need samples and scores).
- `cleanup=False` — keep the buffer DB after recovery (default removes it).

Recovery is **automatic when the run used `eval_set()`** (not plain `eval()`). For `eval()`-based runs that crashed, call `recover_eval_log()` explicitly before re-running from scratch.

## Runtime diagnostics: tracing

Some failures don't appear in `.eval` logs at all (hangs, timeouts, transient errors hidden by retries, slow model generations). Inspect writes a separate set of *trace logs* for runtime diagnostics.

**ALWAYS fetch and read https://inspect.aisi.org.uk/tracing.html.md before doing any tracing work.** Key points:

- Trace logs are written automatically for every eval; the last 10 evaluation runs are preserved.
- Format is JSON Lines, gzip-compressed. Do not read raw; use the CLI:
  - `inspect trace list` — list recent trace logs.
  - `inspect trace anomalies` — actions that didn't terminate properly. Add `--all` to include errors and timeouts.
  - `inspect trace http --failed` — failed HTTP calls (model provider errors, retries).
  - `inspect trace dump --filter <text>` — dump full content for grep-style filtering.

Reach for tracing when:

- An eval hung or was killed before producing a useful log.
- The `.eval` log says `status="success"` but the user suspects something went wrong (silent retries, slow steps).
- You need millisecond-level timings to find a slow tool call or model call.

## Quick decision tree

- "What model/task/config was this run?" → `read_eval_log(path, header_only=True)`
- "Which samples failed or scored low?" → `read_eval_log_sample_summaries(path)` + filter by `s.error` / `s.scores`
- "Show me sample 42 in detail" → `read_eval_log_sample(path, id=42)`
- "Process every sample in this log" → `for s in read_eval_log_samples(path): ...`
- "Compare configs across N log files" → `for log in list_eval_logs(dir): read_eval_log(log, header_only=True)` (safe even for many files since headers are small)
- "Why did the eval fail?" → header status/error first, then sample summaries for `s.error is not None`, then `read_eval_log_sample` on offenders for traceback + `sample.events`
- "What transient errors happened during the run?" → trace logs: `inspect trace http --failed` / `inspect trace anomalies --all`
- "Eval crashed, can I recover unflushed samples?" → `recoverable_eval_logs(dir)` to find candidates, then `recover_eval_log(path)` on each (automatic with `eval_set()`)
- "Search transcripts for patterns across many logs" → this is **Inspect Scout** territory, not raw log reading

---

Last reviewed: 2026-06-05 against inspect_ai v0.3.235
