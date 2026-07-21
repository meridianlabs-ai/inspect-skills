---
name: babysitting-evals
description: >-
  Use for monitoring, diagnosing, and intervening in RUNNING Inspect AI
  evaluations via the `inspect ctl` command-line control channel. Triggers
  when: watching a live eval for stalls/errors/retry failures, checking
  progress of an active eval process, launching an eval you'll monitor in
  parallel, finding problematic samples in a running eval, cancelling a stuck
  sample or task, or retuning a running eval's concurrency or timeouts.
---

# Babysitting Inspect evals via the control channel

Every running `inspect eval` or `inspect eval-set` process binds a local control endpoint by default; `inspect ctl` talks to it so you can observe and direct live evals from a separate shell. Users who pass `--ctl-server=false` opt out and aren't visible to `ctl`.

> **What you can and can't change from `ctl`.** Reads are always safe. The write surface: cancel one sample (`sample cancel`) or a whole task (`task cancel`), retune the launch configuration mid-flight (`config`: concurrency, timeouts, retries, log cadence), force or retune log writes (`task log-flush`, `config --log-buffer`), and toggle the post-completion park (`process keep` / `release`). What `ctl` still can't do is steer *content*: it can't send the agent a message, edit sample state, or interrupt a single generation midway (see Current limitations for `inspect acp`). Stopping the whole **process** is still a signal, not a `ctl` command: the human's Ctrl+C, or you (`kill -INT <pid>`, after confirming with the user). The finalize is shielded, so completed samples are scored and the log finalizes as `cancelled` before teardown. Don't use plain `kill` / SIGTERM; Inspect has no handler for it and unflushed samples are lost. On a starved loop, expect `kill -INT` to be slow (its handler runs on the blocked loop) and the process may then hang in sandbox teardown; because the `.eval` is already finalized by that point, a `kill -9` of the leftover husk is safe *once you've confirmed the log is written*.

> **Confirm the surface with the tool's own docs.** Exact commands, flags, and output shapes live in `inspect ctl --help`, each noun group's `--help`, and the Inspect docs. Run them; the surface evolves. This skill describes the noun-group surface (`ctl task ...`, `ctl sample ...`, `ctl config`, `ctl process ...`) introduced in inspect-ai 0.3.246 (write surface completed in 0.3.247; validated here against 0.3.248). Older versions expose the same reads under flat spellings (`ctl tasks`, `ctl samples`, `ctl events`, ...); those spellings still work on current versions as hidden aliases that print a deprecation note. If `inspect ctl task --help` errors, check the installed version (`pip show inspect-ai`) and propose `pip install -U inspect-ai`. This skill is the *workflow and judgment*.

## Quick loop (the common path)
1. `inspect ctl task list --json` to find running evals (note `task_id`, `pid`, `log_location`). A task is finished exactly when `completed_at` is non-null; don't infer completion from sample counts.
2. `inspect ctl sample list <task> --json` for per-sample status and progress. On later polls, pass the previous envelope's `as_of` via `--active-since` to see only what changed.
3. On trouble: `inspect ctl sample show <task> <sid> --json` for the full error history, or `inspect ctl sample events <task> <sid> --json` for what the sample is doing now.
4. Intervene when warranted, with the user's OK: `inspect ctl sample cancel <task> <sid> <epoch> --action score` resolves one stuck sample while keeping the rest of the task running (`--action error` / `cancel` for other outcomes); `inspect ctl task cancel <task>` stops a whole task; `inspect ctl config` retunes concurrency and timeouts live. Preview any mutation with `--dry-run` first. If the whole *process* has to go, that's still `kill -INT <pid>` (with their OK).

### First-contact recipe
When the user says something like "check on this eval", run the read commands together before reporting back:
```bash
inspect ctl task list --json
inspect ctl sample errors --json         # spans all running tasks
inspect ctl sample list <task> --json    # for any task with errors, or to assess progress
```
Then summarize: how many tasks are running, progress per task, anything errored or retried, anything obviously stalled. Poll on demand: when the user asks, when you need a second `last_activity_at` reading to confirm a possible stall, or when watching for a user-specified event. Don't background-poll a healthy eval.

`ctl` reads retry a busy eval (up to ~2 min, printing "the eval may be busy; retrying") rather than reporting it gone, so a slow read is itself a health signal (a loaded or loop-starved eval; see "Timeouts and event-loop starvation"), not "nothing running". Only a connection-refused means the process actually exited.

### Watching over time: tiered polling
When the user explicitly asks you to **watch an eval over time** (vs. a one-off check), polling IS the task. Don't pick a fixed interval and don't default to "every 30 min". Stay dense at the start, sparse once steady, and anchor each phase on **state signals** rather than the clock: eval timescales vary by orders of magnitude.

**The mechanism to come back.** Polling over time needs a way to actually resume after each interval, rather than waiting on the user to re-prompt. Use your harness's self-scheduled wakeup / periodic check-in feature; in Claude Code, invoke the `/loop` skill in self-paced mode (no fixed interval) so each next wakeup is set off the state signals below. End the loop once the eval finishes or is frozen and fully diagnosed, so it isn't just re-running against a settled state.

| Phase | Cadence | Anchor (the task row's `samples` object from `task list --json`; `retries` from `sample list --json`) |
|---|---|---|
| Spinup (provider auth, dataset fetch, sandbox build; where most failures live) | ~1 min | `samples.completed == 0` |
| Mid-spinup (first samples done, `samples.in_flight` still ramping) | ~5 min | `samples.completed > 0`, `samples.in_flight` not yet stable |
| Steady state (`samples.in_flight` stable, errors flat, samples advancing) | ~15-30 min | `samples.in_flight` stable across at least two polls |
| Near-end (closing reductions / scoring phase) | ~5 min | `samples.completed / samples.total > 0.9` |
| Any error or retry change | snap back to ~1 min for the next poll or two, then resume the prior phase's cadence | `samples.errored` or per-sample `retries` increased since the last poll |

**Two principles alongside the cadence:**

- **Adapt to the eval's timescale.** A 50-sample QA eval can finish inside the spinup window; a 200-sample agentic eval might spend 15 min before its first sample completes. Calibrate against the eval's actual progress, not the wall-clock numbers in the table.
- **Report only on meaningful change.** Dense internal polling does NOT mean talking to the user every minute. Polls are background context-gathering; surface to the user only on: new errors or retries, milestones (first sample done, 25/50/75% complete), suspected stalls, completion. A stream of "still running" messages is worse than silence.

## Commands
Commands are grouped by resource noun: `task`, `sample`, `config`, `process`. A bare noun implies `list` (`inspect ctl task` is `inspect ctl task list`). **Default to `--json` for all reads** when you're going to parse, filter, or compare output across polls; the human tables are summaries that hide fields and truncate. Read responses are envelopes stamped with `as_of` (`{as_of, tasks}`, `{as_of, counts, samples, truncated}`, `{as_of, processes}`); a failed `--json` invocation emits `{"error": {kind, exception, message, status}}` on stdout, so parse errors from the payload instead of scraping stderr.

- `task list`: running tasks across all live processes. Each row carries the selectors other commands take (`task_id`, `pid`) plus `log_location`, `completed_at`, a `samples` progress object, and `keep_alive` (`--json` shows fields the human table hides). `last_activity_at` is a per-sample field, not a task-row field; get it from `sample list`.
- `task log-flush [<task>]`: force an immediate write of the task's buffered completed samples to the log (possibly remote, e.g. S3), making them readable in the `.eval` *now* without waiting for the buffer to fill. Idempotent (nothing pending writes nothing) and given a generous timeout since a remote write can be slow. The retune side is `config --log-buffer` / `--log-shared`.
- `task cancel <task> [--action cancel|score|error] [--dry-run]`: cancel a running task. `--action` decides how in-flight samples resolve: `cancel` (default) interrupts them and finalizes the log with an error status; `score` scores them on the work done so far; `error` marks them errored (with score/error, queued samples are abandoned and the task completes normally). Completed samples are always kept, and an eval-set will not retry a cancelled task. Idempotent; a task between attempts (last attempt errored, retry queued but not started) is rejected, so re-issue once the retry starts.
- `sample list [<task>]`: per-sample rows (status, retries, score, time, tokens, and `idle` since last activity). An omitted TASK spans all running tasks. `--active-since <ts>` is the "what changed since I last looked" delta: feed it the `as_of` from the prior response's envelope. The listing is capped with running samples first; `counts` is always the complete status histogram and `truncated` reports whether rows were dropped (if a delta comes back truncated, re-poll the same value with `--all` before advancing to the new `as_of`). Widen with `--limit N` / `--all`, narrow with `--status <s1,s2>`. The listing spans the eval's full planned sample grid: not-yet-started samples appear with `status: pending` / `queued`, and a just-started sample shows as running with `last_activity_at: null` until it emits its first event.
- `sample errors [<task>]`: one row per sample that errored or was retried, with the latest error message. The natural first call when babysitting ("did anything go wrong?"). An omitted TASK spans all running tasks.
- `sample show <task> <sid> [epoch]`: one sample's summary and full attempt history (every retry, the final error). `--traceback` includes full tracebacks; EPOCH defaults to 1.
- `sample events <task> <sid> [epoch]`: a running sample's transcript events via cursored pull. The default filter is a high-signal tier (`model`, `tool`, `error`, `score`, and also `sandbox`, `approval`, and a few others); pass `--type all` for everything. The way to see *what a sample is actually doing*. Each call returns the envelope `{events, next, done}`. The first call returns a recent tail (`--tail N` to size it, `--from-start` to start at the first event instead); page forward by passing the prior `next` back via `--cursor`. `--since-time` / `--until` bound by unix timestamp; `--limit` caps events per page; `--type` filters (comma-separated); `--full` returns raw events instead of the compact projection. `done: true` means the sample reached a terminal state. Pages are always contiguous from the cursor, so there's no silent-gap case to handle. Old events aren't lost to a ring buffer: evicted events are re-materialized from the realtime buffer for a running sample, and a completed sample's events are read from the recorder buffer then the on-disk log, so paging retrieves an agent's *older* actions without opening the `.eval` yourself. Reads are pull-based, so "immediate" means "within your poll interval".
- `sample cancel <task> <sid> [epoch] [--action score|error|cancel] [--dry-run]`: resolve one running sample; the rest of the task is unaffected. `--action score` (default) runs the scorer on the work done so far; `error` marks it errored; `cancel` records it as cancelled (no scoring, not counted as an error). Idempotent (cancelling a finished sample is a clean no-op). EPOCH is required whenever the task runs more than one epoch: a defaulted epoch would silently cancel a different attempt.
- `config [<task>]`: view (no set options) or retune a running eval's launch configuration mid-flight, under the same spellings as the launch flags: `--max-samples`, `--max-sandboxes`, `--max-subprocesses`, `--max-connections` (optionally scoped with `--model`), any named `concurrency()` limit via `--key NAME LIMIT` (the output lists the registered keys), `--log-buffer` / `--log-shared` (buffering policy for *future* writes; `task log-flush` writes what's already pending), and live retry-loop overrides `--timeout` / `--attempt-timeout` / `--max-retries` (pass `clear` to restore the launch config; a change reaches even generate calls already retrying). Each knob is task- or process-scoped and both the help and the output label which. Lowering a concurrency limit never interrupts running samples: new work waits until in-flight holders drain. `--dry-run` previews any change.
- `process list`: running Inspect processes (`{as_of, processes}`: `pid`, `keep_alive`, hosted tasks). The PID shown is the selector `keep` / `release` take (positional, optional when a single process is running).
- `process keep [PID]`: turn ON the post-completion park; the runtime equivalent of `--ctl-server=keep`, valid regardless of launch flags (including re-asserting keep after a `release`). The process will stay inspectable after its eval finishes instead of exiting. Does NOT change the running eval. Useful when you realize mid-run that you want to interrogate the eval after it completes.
- `process release [PID]`: turn OFF the post-completion park (or release a parked process so it exits). Does NOT cancel anything. `keep` and `release` are last-write-wins, so toggling either way mid-run is safe.

## Who launched it: the exact difference
`ctl` works the same during the run either way, including sample/task cancellation. What differs is **launch flags**, which decide what the human sees and whether the surface survives completion:

| | **User-launched** (interactively) | **You-launched** |
|---|---|---|
| Display / TUI | usually default `--display full`: the human has a TUI and can watch and cancel interactively | you choose: `--detach` or `--display none` (no TUI; you still cancel via `ctl`), or `tmux` + `--display full` if the human wants a live TUI to attach to |
| `--ctl-server=keep` | usually **omitted**: the process exits when the eval finishes and the `ctl` surface vanishes | optional; only if you want to interrogate the eval *after* it finishes. Toggleable mid-run via `inspect ctl process keep` / `release`, so missing it at launch isn't permanent. |
| Config visibility | partial: `ctl task list --json` gives `log_location` and `model`, `ctl config` shows the retunable knobs, ask the user for the rest | full: you picked `--log-dir`, `--ctl-server`, and display |
| Stop the whole run | the human (Ctrl+C) | `inspect ctl task cancel` per task, or `kill -INT <pid>` for the process (with their OK) |

## Use case: monitoring a run the USER started
Use `ctl` exactly as in the Quick loop; disambiguate by `task_id` if several are running. `ctl task list --json` gives each run's `log_location`, so you can find logs without asking. For *reading* those logs (works in-progress too), use the **`reading-logs`** skill; that's for results and detail, not live monitoring.

You can monitor and diagnose freely, but there's no ownership check on the write surface, so treat mutations on their run as **theirs to approve**: propose the exact command (`sample cancel` / `task cancel` / `config`) and run it on their OK, or point them at the sample in their TUI. Don't `release` their process unless they ask: issued while the eval is still running, `release` clears their keep-alive intent so the process exits when the eval finishes (last-write-wins, so a `keep` can restore it, but it's still their call).

## Use case: the user asks you to BOTH launch and babysit
Cancellation no longer requires a TUI (`ctl` covers it), so the launch question is just: does the human want a **live TUI** to watch and interact with? **Ask (AskUserQuestion) before launching.**

**If no TUI is wanted, launch detached:**
```bash
/path/to/venv/bin/inspect eval-set <file.py@task> --model <m> --log-dir <dir> --detach
```
`--detach` backgrounds the eval so it outlives your shell and prints a JSON `launch` record once the control endpoint is bound: `run_id`, `pid`, `log_dir`, the control socket path, and an `output_file` that collects the process output (its last line is a `done` record with each task's status and log location). A non-null `control` in the launch record guarantees `inspect ctl` is usable immediately, so there's no need to sleep-and-retry after launch. Monitor via the Quick loop; cancel with `ctl task cancel`; stop the process with `kill -INT <pid>` if it comes to that. (A foreground launch with `--json` emits the same launch/done records if you want to hold the process in your own shell.)

**If the human wants the TUI**, launch inside a **detached `tmux` session running the full TUI**:
```bash
# If tmux isn't installed, install it first:
#   macOS: brew install tmux
#   Debian/Ubuntu: sudo apt-get install -y tmux
tmux new-session -d -s eval_<name> \
  '/path/to/venv/bin/inspect eval-set <file.py@task> --model <m> --display full --log-dir <dir>'
# tell the user:  tmux attach -t eval_<name>     (detach again with Ctrl-b then d)
```
The full TUI renders in the detached session and you keep monitoring via `ctl` in parallel; from the TUI the user can watch progress and cancel interactively. Install `tmux` yourself if it's missing. (If the user has a Flow spec instead of an `eval-set` script, see the `inspect-flow` section.)

Either way, default to **`inspect eval-set`** (not `inspect eval`) for more robust retry, recovery, and resume. `--log-dir` is required; it's the resume key.

> **Don't try to read the eval state via tmux.** `tmux attach` from your non-TTY shell fails with `open terminal failed: not a terminal`, and `tmux capture-pane -p` of an Inspect TUI returns only the chrome (title, tab headers, footer): the per-sample body is rendered by Textual at terminal coordinates that don't appear in a detached pane. Use `ctl` for visibility. tmux exists here so the **user** can attach and use the TUI, and so you can confirm the session is alive or clean it up.
>
> **Surface the session name and these commands to the user** so they can manage it independently:
> - `tmux ls`: list running sessions.
> - `tmux attach -t eval_<name>`: interact with the TUI (detach with Ctrl-b then d).
> - `tmux kill-session -t eval_<name>`: force-clean a stuck or orphaned session.
>
> **Avoid name collisions on reruns.** `tmux new-session -s eval_<name>` fails with `duplicate session: eval_<name>` if that name is already in use, so pre-check with `tmux has-session -t eval_<name>`. Don't *reuse* an existing session for a fresh launch: a leftover stale Inspect process can keep its `ctl` endpoint alive and confuse `ctl task list`. For each new launch, **either pick a fresh suffix** (e.g. `eval_<name>_<YYYYMMDD-HHMM>`) **or kill the old session first** (`tmux kill-session -t eval_<name>`) once the user confirms it's stale.
>
> A tmux launch has no `launch` record, so give Inspect a few seconds to bind the control endpoint before declaring "nothing running" from `ctl task list --json`. If the user is already inside tmux, the nested behavior can confuse both of you; suggest they detach from their outer session first.

### Confirm `--continue-on-fail` before launch
Always confirm the user's intent on **`--continue-on-fail`**. Default is fail-fast (the run stops on the first sample error). The opt-in keeps the run going, marks the log `error`, and leaves failed samples retryable and resumable later. The two paths produce very different runs and are easy to set wrong, so ask explicitly. Most other parameters (model, limits, epochs, `--log-dir`) are typically already encoded in the user's `eval_set()` script or Flow spec; confirm only what's missing or being overridden, and **record the exact command** for reproducibility.

## Diagnosing issues
- **Stalls**: judge by **`last_activity_at` deltas across at least two polls**, not a single snapshot, and NOT `total_tokens` / `message_count` (those sit at 0 or 1 during a long generation). **Idle is not the same as stall.** `last_activity_at` advances only when an event is emitted, so a single in-flight call (model generation with extended thinking, a sandbox `exec`, a slow tool) can legitimately leave it frozen for minutes. Calibrate the window to **what the last event was**:

  | Last event in flight | Suspect if idle for | Alarm if idle for |
  |---|---|---|
  | ModelEvent (plain generation) | 30s | 2m |
  | ModelEvent (extended thinking) | 2m | 10m |
  | ToolEvent (tool / network call) | 2m | 10m |
  | SandboxEvent (sandbox `exec`) | 5m | 20m |

  These are rough defaults; scale up for tasks where samples routinely take longer. Alert only after corroborating across the window AND looking at the last event type. Don't hardcode the poll interval. One caveat: `last_activity_at` measures *motion*, not *progress*, so a retry storm or an agent stuck in a loop keeps it advancing (events keep flowing) while nothing finishes; when it looks healthy but you're unsure, also check whether TOTAL `completed` is actually advancing across polls, not just activity. For a sample that is confirmed stuck and burning tokens, the remediation is `sample cancel` (default `--action score` keeps the work done so far); propose it to the user rather than acting unilaterally.
- **Errors / retry-exhaustion**: `sample errors --json` for the triage list; `sample show <task> <sid> --json` for the full attempt history and final error; `sample events <task> <sid> --json` for the in-flight transcript leading up to the failure. When a sample errors after exhausting retries, notify immediately with the **exact error message** and a short **analysis** (likely cause; input-specific vs task-wide). A retried-then-passed sample (`status: completed`, `retries>0`) is a success, but still surface that it erred. If retries are being burned by a too-tight timeout, `ctl config --timeout` / `--attempt-timeout` / `--max-retries` can be retuned live instead of relaunching.
- **Timeouts and event-loop starvation**: an eval process runs *one* asyncio event loop, shared by every sample's model / tool / sandbox calls, the logging and flush machinery, AND the control server. When something monopolizes that loop without yielding (serializing a large transcript, a slow log flush to remote storage, sheer concurrency, or being GIL-bound to one core), everything else stalls, including new network handshakes. That is event-loop starvation, and the underlying `httpx` exception (in the `ctl sample show --json` traceback) tells you which problem you have:

  | httpx exception | Means | What to do |
  |---|---|---|
  | `ConnectTimeout` | Loop too starved to even complete a handshake | Self-inflicted: lower concurrency **live** with `inspect ctl config --max-samples N` (running samples drain; new work waits). The adaptive-connections controller scales *down* only on rate limits, NOT on timeouts, so a ConnectTimeout storm will not self-correct; you must reduce load. Expect the `config` write itself to be slow on a starved loop. |
  | `ReadTimeout` | Handshake fine, generation genuinely slow | Usually benign; raise the model timeout (`ctl config --timeout`) or wait. Not a concurrency problem. |
  | `429` / rate limit | Real server-side limit | The controller backs off automatically; largely self-heals. |

  Signals of starvation with no extra tooling: `ctl` reads themselves going slow or printing "the eval may be busy; retrying", `ConnectTimeout`s in the errors, and a throughput stall (TOTAL `completed` flat across polls while tokens keep moving). For the exception breakdown and rate over time, use the trace-log commands from the **`reading-logs`** skill (`inspect trace http --failed`, `inspect trace anomalies --all`). Caution: `ctl task log-flush` and a low `--log-shared` interval both add loop-taxing I/O, so don't pile them onto an already-starved loop.
- **User-defined event-stream watches**: `ctl sample events` lets you watch *what a sample is doing*. If the user gave a specific goal ("watch for X"), watch for it; otherwise don't proactively ask unless the eval looks weird. Examples worth flagging when relevant: **repetition / "submit loops"** (an agent repeatedly sending the same `submit` *message* instead of calling the `submit` *tool*, so it never submits and burns tokens), unintended shortcut solutions, particular tool-call arguments, signs of reward hacking, or progress toward a stated goal. Watch via `ctl sample events <task> <sid> --cursor <next> --json`.
  - **Be faithful about confidence.** Some of these you can flag reliably (a literally repeated call); most you can only weakly infer and may lack context to judge. Say so: label low-confidence signals as such, tell the user what you can and can't detect rather than over-claiming, and point them to the sample (via `sample events`, or their TUI) to judge. If the verdict is "kill it", `sample cancel` is the lever, on their OK.

## Resource constraints with Docker sandboxes
When `max_samples` is high and each sample runs in its own Docker container (a common pattern for code- or agent-evals), local resources become the bottleneck before the model does.

**Pre-launch sanity check**: if the user is setting `max_samples > ~10` with a Docker sandbox, surface the math before launch.

- Each container carries Inspect overhead plus the task's runtime (Python, tools, model client). Roughly 200-500 MB resident per container is typical; more for tasks that pull in heavy libraries or build code.
- `max_samples × per-container MB` should fit comfortably in available RAM with headroom. On a 32 GB Mac, ~50 light containers is fine; 5 heavy containers can already OOM.
- Docker Desktop on macOS / Windows has its own resource cap (Settings → Resources). If `max_samples=20` and Docker is allocated 8 GB, the eval will thrash regardless of host RAM.

**Quick host checks** when you suspect pressure:

```bash
docker stats --no-stream                              # CPU / mem / I/O per container
docker ps --filter "label=inspect"                    # any zombie containers?
# macOS:
vm_stat | awk '/Pages free/ {print "free:", $3 * 4096 / 1024 / 1024, "MB"}'
# Linux:
free -m | head -2
```

**Remediation patterns** (recommend; don't act unilaterally):
- **Drop `max_samples`**: the simplest dial, and it no longer needs a relaunch: `inspect ctl config --max-samples N` retunes the running eval (in-flight samples finish; new work respects the lower cap). `--max-sandboxes` is the same dial for sandbox pressure specifically.
- **Increase Docker Desktop's memory/CPU allocation** (macOS / Windows). Often the actual cap.
- **Switch to a remote sandbox** (`inspect_sandboxes`, k8s, Proxmox); see `map-inspect-packages` for routing.
- **Add `--time-limit`** per sample so a stuck container can't hold resources indefinitely.

## Reading results and summarizing
Give the user a **summary**, not raw counts: per-model results, **outliers** (samples far slower or more tokens than the rest), and **flag that errors happened even if retries fixed them**. For **log files** (in-progress or finished), use the **`reading-logs`** skill. Prefer `read_eval_log(..., header_only=True)` and read sample detail selectively; `.eval` logs get large, and reading several at once can exhaust memory. If a recently-completed sample isn't in the `.eval` yet, its record may still be buffered: run `inspect ctl task log-flush` to force the write, then read it. (`ctl sample events` sees completed samples without a flush; the flush is only needed for reading the log file.)

## `inspect-flow`
If the user already has a Flow spec (a Python file describing an eval-set for [inspect-flow](https://meridianlabs-ai.github.io/inspect_flow/)), launch it with `flow run <path/to/spec.py>`. A Flow spec runs an `eval-set` under the hood, so everything in this skill applies: `ctl task list` sees the run, all read and write commands work, and diagnosing stalls and errors is identical. `flow run` doesn't expose `--ctl-server=keep`, but that's no longer a gap: park the process at runtime with `inspect ctl process keep <pid>` if you want to interrogate it after completion, and `release` it when done.

## Cleanup at end of session
Any process with keep-alive set (`--ctl-server=keep` at launch, or `inspect ctl process keep` at runtime) parks after the eval finishes and waits **indefinitely** for `inspect ctl process release`; it won't exit on its own. Spotting keep-alive processes is a one-liner:

```bash
inspect ctl process list --json | jq '.processes[] | select(.keep_alive) | {pid, tasks}'
```

Before ending the babysitting session, sweep for keep-alive processes and ask the user if they're done interrogating each. Then release:

```bash
inspect ctl process release <pid>
```

For parked runs the user launched themselves: defer entirely. Don't release someone else's parked process unless they ask you to. (`keep` and `release` are last-write-wins, so they could always re-`keep` if a release was premature, but it's still their intent to change.)

## Current limitations
- **`ctl` can't steer content.** Its writes stop at the workflow level: cancel, retune, park, flush. To *steer* a running sample, the write surface is **`inspect acp`**: it lets a human or an attached agent send a steering message, interrupt generation, or cancel a tool call, even when the eval was launched headless. Enable on launch with `inspect eval[-set] --acp-server` (off by default). Attach from another shell with `inspect acp` (lists running ACP-enabled evals; pin one via `--task-id` / `--sample-id` / `--epoch`). Full surface: <https://inspect.aisi.org.uk/intervention.html>. This skill stays scoped to `ctl`; reach for ACP when the user wants to redirect an agent rather than resolve or cancel its sample.
- **`sample events` is pull-based.** Alerts are bounded by your poll interval (in practice, the time between assistant turns); there's no server push, so "watch for X" means checking on each poll.
- **No decoupled `inspect tui`.** For a detachable human view of an eval *you* launched, use `tmux` + `--display full` (above) or `inspect view start --log-dir <dir>` (a separate viewer; closing it doesn't halt the eval). `--detach` gives you a background process, not a human view.
