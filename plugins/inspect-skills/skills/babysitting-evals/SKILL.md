---
name: babysitting-evals
description: >-
  Use for monitoring and diagnosing RUNNING Inspect AI evaluations via the
  `inspect ctl` command-line control channel. Triggers when: watching a live
  eval for stalls/errors/retry failures, checking progress of an active eval
  process, launching an eval you'll monitor in parallel, or finding problematic
  samples in a running eval.
---

# Babysitting Inspect evals via the control channel

Every running `inspect eval` or `inspect eval-set` process binds a local control endpoint by default; `inspect ctl` talks to it so you can observe live evals from a separate shell. Users who pass `--ctl-server=false` opt out and aren't visible to `ctl`.

> **In-progress feature, expect gaps.** The control channel can't change the eval's **computation or results**: you observe via `ctl`, and the state you can mutate is limited to the **log-write cadence** (`flush` / `buffer`, see Commands) and the process's post-completion park (`keep` / `release`). None of these alter the running eval's work. What's possible today to change a running eval:
> - **Cancel an individual sample or task**: a **human**, from the eval's **TUI**.
> - **Stop the whole eval/process**: the human (Ctrl+C), or you (`kill -INT <pid>`, after confirming with the user). Same graceful path as Ctrl+C: the finalize is shielded, so completed samples are scored and the log finalizes as `cancelled` before teardown. Don't use plain `kill` / SIGTERM; Inspect has no handler for it and unflushed samples are lost. On a starved loop, expect `kill -INT` to be slow (its handler runs on the blocked loop) and the process may then hang in sandbox teardown; because the `.eval` is already finalized by that point, a `kill -9` of the leftover husk is safe *once you've confirmed the log is written*.

> **Confirm the surface with the tool's own docs.** Exact commands, flags, and output shapes live in `inspect ctl --help`, each subcommand's `--help`, and the Inspect docs. Run them; the surface evolves. This skill is the *workflow and judgment*.

## Quick loop (the common path)
1. `inspect ctl tasks --json` to find running evals (note `task_id`, `pid`, `log_location`).
2. `inspect ctl samples <task> --json` for per-sample status and progress. Repeat to track.
3. On trouble: `inspect ctl sample <task> <sid> --json` for the full error history, or `inspect ctl events <task> <sid> --json` for what the sample is doing now.
4. Can't fix via `ctl`? Hand off: tell the user **which task and sample** (id + epoch) and **what you saw**, then either point them at the sample in their TUI to cancel, or stop the run yourself (`kill -INT <pid>`, with their OK).

### First-contact recipe
When the user says something like "check on this eval", run the read commands together before reporting back:
```bash
inspect ctl tasks --json
inspect ctl errors <task> --json    # for each running task
inspect ctl samples <task> --json   # for any task with errors, or to assess progress
```
Then summarize: how many tasks are running, progress per task, anything errored or retried, anything obviously stalled. Poll on demand: when the user asks, when you need a second `last_activity_at` reading to confirm a possible stall, or when watching for a user-specified event. Don't background-poll a healthy eval.

`ctl` reads retry a busy eval (up to ~2 min, printing "the eval may be busy; retrying") rather than reporting it gone, so a slow read is itself a health signal (a loaded or loop-starved eval; see "Timeouts and event-loop starvation"), not "nothing running". Only a connection-refused means the process actually exited.

### Watching over time: tiered polling
When the user explicitly asks you to **watch an eval over time** (vs. a one-off check), polling IS the task. Don't pick a fixed interval and don't default to "every 30 min". Stay dense at the start, sparse once steady, and anchor each phase on **state signals** rather than the clock: eval timescales vary by orders of magnitude.

**The mechanism to come back.** Polling over time needs a way to actually resume after each interval, rather than waiting on the user to re-prompt. Use your harness's self-scheduled wakeup / periodic check-in feature; in Claude Code, invoke the `/loop` skill in self-paced mode (no fixed interval) so each next wakeup is set off the state signals below. End the loop once the eval finishes or is frozen and fully diagnosed, so it isn't just re-running against a settled state.

| Phase | Cadence | Anchor (from `tasks --json` + `samples --json`) |
|---|---|---|
| Spinup (provider auth, dataset fetch, sandbox build; where most failures live) | ~1 min | `samples.completed == 0` |
| Mid-spinup (first samples done, `in_flight` still ramping) | ~5 min | `completed > 0`, `in_flight` not yet stable |
| Steady state (`in_flight` stable, errors flat, samples advancing) | ~15-30 min | `in_flight` stable across at least two polls |
| Near-end (closing reductions / scoring phase) | ~5 min | `completed / total > 0.9` |
| Any error or retry change | snap back to ~1 min for the next poll or two, then resume the prior phase's cadence | `errored` or per-sample `retries` increased since the last poll |

**Two principles alongside the cadence:**

- **Adapt to the eval's timescale.** A 50-sample QA eval can finish inside the spinup window; a 200-sample agentic eval might spend 15 min before its first sample completes. Calibrate against the eval's actual progress, not the wall-clock numbers in the table.
- **Report only on meaningful change.** Dense internal polling does NOT mean talking to the user every minute. Polls are background context-gathering; surface to the user only on: new errors or retries, milestones (first sample done, 25/50/75% complete), suspected stalls, completion. A stream of "still running" messages is worse than silence.

## Commands
Today's surface: read commands `tasks`, `samples`, `sample`, `errors`, `events`, plus write commands `flush` / `buffer` (log-write cadence) and `keep` / `release` (post-completion park). **Default to `--json` for all reads** when you're going to parse, filter, or compare output across polls; the human tables are summaries that hide fields and truncate.

- `tasks`: running evals. The human table shows `task_id` / `task` / `samples` / `started`, with a keep-alive footer (`on` / `off` / `mixed`). `pid` / `log_location` / `last_activity_at` / `completed_at` / `keep_alive` are in `--json` only.
- `samples`: per-sample table (status, retries, score, time, tokens, and `idle` since last activity). `--active-since <ts>` gives a "what changed since I last looked" delta. `--json` exposes raw `last_activity_at` for delta math. A sample doesn't appear here until it has emitted at least one event, so a sample still in solver setup can be `in_flight` in `tasks` without showing up in `samples`; the polling rule above still applies (don't loop, come back to it when the user asks for an update).
- `sample`: one sample's full attempt history (every retry, the final error).
- `errors`: task-wide list of every sample that errored or was retried. The natural first call when babysitting ("did anything go wrong?").
- `events`: a running sample's transcript events (`model` / `tool` / `error` / `score`) via cursored pull. The way to see *what a sample is actually doing*. Each call returns the envelope `{events, next, done}`. Page forward by passing the prior `next` back via `--since`. `--tail N` peeks at the latest; `--type` filters (comma-separated, `*` for all); `--full` returns raw events instead of the compact projection. `done: true` means the sample reached a terminal state. Pages are always contiguous from the cursor, so there's no silent-gap case to handle. Old events aren't lost to a ring buffer: evicted events are re-materialized from the realtime buffer for a running sample, and a completed sample's events are read from the recorder buffer then the on-disk log, so `ctl events --since` retrieves an agent's *older* actions without opening the `.eval` yourself. Reads are pull-based, so "immediate" means "within your poll interval".
- `keep [--pid N]`: turn ON the post-completion park for a process launched WITHOUT `--ctl-server=keep` (canonical spelling; `keep-alive` is a legacy alias). The process will stay inspectable after its eval finishes instead of exiting. Does NOT change the running eval. Useful when you realize mid-run that you want to interrogate the eval after it completes.
- `release [--pid N]`: turn OFF the post-completion park (or release a parked process so it exits). Does NOT cancel anything. `keep` and `release` are last-write-wins, so toggling either way mid-run is safe.
- `flush [<task>]`: force an immediate write of the eval's buffered completed samples to the log (possibly remote, e.g. S3). Completed samples normally accumulate until the buffer fills; flush makes them readable in the `.eval` *now* without waiting. Idempotent (nothing pending writes nothing) and given a generous timeout since a remote write can be slow. Reach for it when you want to read recent completions from the log mid-run (see Reading results).
- `buffer [<task>]`: view or retune the sample-buffer parameters. No options shows the current config, including `pending` (samples buffered but not yet written). `--samples N` sets how many completed samples buffer before a log write (lower means completed results land in the log sooner, at the cost of more frequent writes); it affects *future* writes only and does NOT flush what's already pending (use `flush` for that). `--shared S` sets the realtime-view sync interval in seconds: how often the live in-progress event buffer is synced to a shared/remote log dir so someone running `inspect view` on another machine sees updates (off by default). Both are last-write-wins.

## Who launched it: the exact difference
`ctl` works the same during the run either way. What differs is **two launch flags**, which decide who (if anyone) can intervene and whether the surface survives completion:

| | **User-launched** (interactively) | **You-launched** |
|---|---|---|
| Display / TUI | usually default `--display full`: the human has a TUI and can cancel a sample or task | you choose: `--display none` means no TUI and nobody can cancel a sample or task; or `tmux` + `--display full` lets the human attach and cancel |
| `--ctl-server=keep` | usually **omitted**: the process exits when the eval finishes and the `ctl` surface vanishes | optional; only if you want to interrogate the eval *after* it finishes. Toggleable mid-run via `inspect ctl keep` / `release`, so missing it at launch isn't permanent. |
| Config visibility | partial: `ctl tasks --json` gives `log_location` and `model`, ask the user for the rest | full: you picked `--log-dir`, `--ctl-server`, and display |
| Stop the whole run | the human (Ctrl+C) | you (`kill -INT <pid>`, with their OK) |

## Use case: monitoring a run the USER started
Use `ctl` exactly as in the Quick loop; disambiguate by `task_id` if several are running. `ctl tasks --json` gives each run's `log_location`, so you can find logs without asking. For *reading* those logs (works in-progress too), use the **`reading-logs`** skill; that's for results and detail, not live monitoring.

You can monitor and diagnose, but **shouldn't** `release` their run. There's no ownership check today, but releasing a still-running eval is a no-op anyway (parking only happens post-completion). If you find an issue, point them at the sample in their TUI.

## Use case: the user asks you to BOTH launch and babysit
Headless means no TUI, which means no one can cancel a sample or task (see the table). So before launching, **ask (AskUserQuestion) whether to preserve TUI access**, explaining that per-sample/task cancellation is only possible from the eval's TUI.

If they want it, launch inside a **detached `tmux` session running the full TUI**:
```bash
# If tmux isn't installed, install it first:
#   macOS: brew install tmux
#   Debian/Ubuntu: sudo apt-get install -y tmux
tmux new-session -d -s eval_<name> \
  '/path/to/venv/bin/inspect eval-set <file.py@task> --model <m> --display full --log-dir <dir>'
# tell the user:  tmux attach -t eval_<name>     (detach again with Ctrl-b then d)
```
Default to **`inspect eval-set`** (not `inspect eval`) for more robust retry, recovery, and resume. `--log-dir` is required; it's the resume key. The full TUI renders in the detached session and you keep monitoring via `ctl` in parallel; from the TUI the user can cancel an individual sample or task. Install `tmux` yourself if it's missing. (If the user has a Flow spec instead of an `eval-set` script, see the `inspect-flow` section.)

> **Don't try to read the eval state via tmux.** `tmux attach` from your non-TTY shell fails with `open terminal failed: not a terminal`, and `tmux capture-pane -p` of an Inspect TUI returns only the chrome (title, tab headers, footer): the per-sample body is rendered by Textual at terminal coordinates that don't appear in a detached pane. Use `ctl` for visibility. tmux exists here so the **user** can attach and use the TUI's keystrokes (cancel a sample, etc.), and so you can confirm the session is alive or clean it up.
>
> **Surface the session name and these commands to the user** so they can manage it independently:
> - `tmux ls`: list running sessions.
> - `tmux attach -t eval_<name>`: interact with the TUI (detach with Ctrl-b then d).
> - `tmux kill-session -t eval_<name>`: force-clean a stuck or orphaned session.
>
> **Avoid name collisions on reruns.** `tmux new-session -s eval_<name>` fails with `duplicate session: eval_<name>` if that name is already in use, so pre-check with `tmux has-session -t eval_<name>`. Don't *reuse* an existing session for a fresh launch: a leftover stale Inspect process can keep its `ctl` endpoint alive and confuse `ctl tasks`. For each new launch, **either pick a fresh suffix** (e.g. `eval_<name>_<YYYYMMDD-HHMM>`) **or kill the old session first** (`tmux kill-session -t eval_<name>`) once the user confirms it's stale.
>
> After launch, give Inspect a few seconds to bind the control endpoint before declaring "nothing running" from `ctl tasks --json`. If the user is already inside tmux, the nested behavior can confuse both of you; suggest they detach from their outer session first.

If TUI access isn't wanted, launch headless (`--display none`). Per-sample/task cancellation needs the TUI, so it won't be possible. The whole run can still be stopped (`kill -INT <pid>`, confirm first).

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

  These are rough defaults; scale up for tasks where samples routinely take longer. Alert only after corroborating across the window AND looking at the last event type. Don't hardcode the poll interval. One caveat: `last_activity_at` measures *motion*, not *progress*, so a retry storm or an agent stuck in a loop keeps it advancing (events keep flowing) while nothing finishes; when it looks healthy but you're unsure, also check whether TOTAL `completed` is actually advancing across polls, not just activity.
- **Errors / retry-exhaustion**: `errors --json` for the triage list; `sample <task> <sid> --json` for the full attempt history and final error; `events <task> <sid> --json` for the in-flight transcript leading up to the failure. When a sample errors after exhausting retries, notify immediately with the **exact error message** and a short **analysis** (likely cause; input-specific vs task-wide). A retried-then-passed sample (`status: completed`, `retries>0`) is a success, but still surface that it erred.
- **Timeouts and event-loop starvation**: an eval process runs *one* asyncio event loop, shared by every sample's model / tool / sandbox calls, the logging and flush machinery, AND the control server. When something monopolizes that loop without yielding (serializing a large transcript, a slow log flush to remote storage, sheer concurrency, or being GIL-bound to one core), everything else stalls, including new network handshakes. That is event-loop starvation, and the underlying `httpx` exception (in the `ctl sample --json` traceback) tells you which problem you have:

  | httpx exception | Means | What to do |
  |---|---|---|
  | `ConnectTimeout` | Loop too starved to even complete a handshake | Self-inflicted: cap `max_samples` / concurrency. The adaptive-connections controller scales *down* only on rate limits, NOT on timeouts, so a ConnectTimeout storm will not self-correct; you must reduce load. |
  | `ReadTimeout` | Handshake fine, generation genuinely slow | Usually benign; raise the model timeout or wait. Not a concurrency problem. |
  | `429` / rate limit | Real server-side limit | The controller backs off automatically; largely self-heals. |

  Signals of starvation with no extra tooling: `ctl` reads themselves going slow or printing "the eval may be busy; retrying", `ConnectTimeout`s in the errors, and a throughput stall (TOTAL `completed` flat across polls while tokens keep moving). For the exception breakdown and rate over time, use the trace-log commands from the **`reading-logs`** skill (`inspect trace http --failed`, `inspect trace anomalies --all`). Caution: `ctl flush` and a low `--shared` interval both add loop-taxing I/O, so don't pile them onto an already-starved loop.
- **User-defined event-stream watches**: `ctl events` lets you watch *what a sample is doing*. If the user gave a specific goal ("watch for X"), watch for it; otherwise don't proactively ask unless the eval looks weird. Examples worth flagging when relevant: **repetition / "submit loops"** (an agent repeatedly sending the same `submit` *message* instead of calling the `submit` *tool*, so it never submits and burns tokens), unintended shortcut solutions, particular tool-call arguments, signs of reward hacking, or progress toward a stated goal. Watch via `ctl events <task> <sid> --since <cursor> --json`.
  - **Be faithful about confidence.** Some of these you can flag reliably (a literally repeated call); most you can only weakly infer and may lack context to judge. Say so: label low-confidence signals as such, tell the user what you can and can't detect rather than over-claiming, and point them to the sample (TUI) to judge and act.

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
- **Drop `max_samples`**: the simplest dial. Smaller value = fewer concurrent containers = less pressure.
- **Increase Docker Desktop's memory/CPU allocation** (macOS / Windows). Often the actual cap.
- **Switch to a remote sandbox** (`inspect_sandboxes`, k8s, Proxmox); see `map-inspect-packages` for routing.
- **Add `--time-limit`** per sample so a stuck container can't hold resources indefinitely.

## Reading results and summarizing
Give the user a **summary**, not raw counts: per-model results, **outliers** (samples far slower or more tokens than the rest), and **flag that errors happened even if retries fixed them**. For **log files** (in-progress or finished), use the **`reading-logs`** skill. Prefer `read_eval_log(..., header_only=True)` and read sample detail selectively; `.eval` logs get large, and reading several at once can exhaust memory. If a recently-completed sample isn't in the `.eval` yet, its record may still be buffered: run `inspect ctl flush` to force the write, then read it. (`ctl events` sees completed samples without a flush; flush is only needed for reading the log file.)

## `inspect-flow`
If the user already has a Flow spec (a Python file describing an eval-set for [inspect-flow](https://meridianlabs-ai.github.io/inspect_flow/)), launch it with `flow run <path/to/spec.py>`. A Flow spec runs an `eval-set` under the hood, so everything in this skill applies: `ctl tasks` sees the run, all read commands work, and diagnosing stalls and errors is identical. One current caveat: `flow run` doesn't expose `--ctl-server=keep`, so the `ctl` surface vanishes the moment flow exits. Fine for live monitoring; not yet usable for post-completion interrogation.

## Cleanup at end of session
Any process with keep-alive set (`--ctl-server=keep` at launch, or `inspect ctl keep --pid` at runtime) parks after the eval finishes and waits **indefinitely** for `inspect ctl release`; it won't exit on its own. `tasks --json` reports the current intent in the `keep_alive` field per task (and an `on` / `off` / `mixed` footer on the human table), so spotting keep-alive processes is a one-liner:

```bash
inspect ctl tasks --json | jq '.[] | select(.keep_alive) | {pid, task, completed_at}'
```

Before ending the babysitting session, sweep for keep-alive processes and ask the user if they're done interrogating each. Then release:

```bash
inspect ctl release --pid <pid>
```

For parked runs the user launched themselves: defer entirely. Don't release someone else's parked process unless they ask you to. (`keep` and `release` are last-write-wins, so they could always re-`keep` if a release was premature, but it's still their intent to change.)

## Current limitations
- **`ctl` can't steer the running eval.** `ctl`'s writes only touch logging and the post-completion park (see Commands); they can't change the eval's computation, results, or trajectory. To actually *steer* a running eval, the write surface is **`inspect acp`**: it lets a human or an attached agent send a steering message, interrupt generation, cancel a tool call, or cancel a sample, even when the eval was launched headless. Enable on launch with `inspect eval[-set] --acp-server` (off by default). Attach from another shell with `inspect acp` (lists running ACP-enabled evals; pin one via `--task-id` / `--sample-id` / `--epoch`). Full surface: <https://inspect.aisi.org.uk/intervention.html>. This skill stays scoped to `ctl`; reach for ACP when the user wants to delegate the intervention rather than do it in their TUI.
- **`events` is pull-based.** Alerts are bounded by your poll interval (in practice, the time between assistant turns); there's no server push, so "watch for X" means checking on each poll.
- **No decoupled `inspect tui`.** For a detachable human view of an eval *you* launched, use `tmux` + `--display full` (above) or `inspect view start --log-dir <dir>` (a separate viewer; closing it doesn't halt the eval).
