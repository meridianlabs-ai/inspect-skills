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

> **In-progress feature, expect gaps.** The control channel is **read-only**: you observe via `ctl` and `release` finished processes, but you can't mutate a running eval through it. What's possible today to change a running eval:
> - **Cancel an individual sample or task**: a **human**, from the eval's **TUI**.
> - **Stop the whole eval/process**: the human (Ctrl+C), or you (`kill -INT <pid>`, after confirming with the user). Same graceful path as Ctrl+C: completed samples are scored and the log finalizes as `cancelled`. Don't use plain `kill` / SIGTERM; Inspect has no handler for it and unflushed samples are lost.

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

## Commands
Read-only commands today: `tasks`, `samples`, `sample`, `errors`, `events`, `release`. **Default to `--json` for all of these** when you're going to parse, filter, or compare output across polls; the human tables are summaries that hide fields and truncate.

- `tasks`: running evals. The human table shows `task_id` / `task` / `samples` / `started`. `pid` / `log_location` / `last_activity_at` / `completed_at` are in `--json` only.
- `samples`: per-sample table (status, retries, score, time, tokens, and `idle` since last activity). `--active-since <ts>` gives a "what changed since I last looked" delta. `--json` exposes raw `last_activity_at` for delta math. A sample doesn't appear here until it has emitted at least one event, so a sample still in solver setup can be `in_flight` in `tasks` without showing up in `samples`; the polling rule above still applies (don't loop, come back to it when the user asks for an update).
- `sample`: one sample's full attempt history (every retry, the final error).
- `errors`: task-wide list of every sample that errored or was retried. The natural first call when babysitting ("did anything go wrong?").
- `events`: a running sample's transcript events (`model` / `tool` / `error` / `score`) via cursored pull. The way to see *what a sample is actually doing*. Each call returns the envelope `{events, next, done}`. Page forward by passing the prior `next` back via `--since`. `--tail N` peeks at the latest; `--type` filters (comma-separated, `*` for all); `--full` returns raw events instead of the compact projection. `done: true` means the sample reached a terminal state. Pages are always contiguous from the cursor, so there's no silent-gap case to handle. Push, `--follow`, and SSE aren't shipped, so "immediate" means "within your poll interval".
- `release`: free a finished `--ctl-server=keep-alive` process. Does NOT cancel anything.

## Who launched it: the exact difference
`ctl` works the same during the run either way. What differs is **two launch flags**, which decide who (if anyone) can intervene and whether the surface survives completion:

| | **User-launched** (interactively) | **You-launched** |
|---|---|---|
| Display / TUI | usually default `--display full`: the human has a TUI and can cancel a sample or task | you choose: `--display none` means no TUI and nobody can cancel a sample or task; or `tmux` + `--display full` lets the human attach and cancel |
| `--ctl-server=keep-alive` | usually **omitted**: the process exits when the eval finishes and the `ctl` surface vanishes | optional; only if you want to interrogate the eval *after* it finishes (rare) |
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

  These are rough defaults; scale up for tasks where samples routinely take longer. Alert only after corroborating across the window AND looking at the last event type. Don't hardcode the poll interval.
- **Errors / retry-exhaustion**: `errors --json` for the triage list; `sample <task> <sid> --json` for the full attempt history and final error; `events <task> <sid> --json` for the in-flight transcript leading up to the failure. When a sample errors after exhausting retries, notify immediately with the **exact error message** and a short **analysis** (likely cause; input-specific vs task-wide). A retried-then-passed sample (`status: completed`, `retries>0`) is a success, but still surface that it erred.
- **User-defined event-stream watches**: `ctl events` lets you watch *what a sample is doing*. If the user gave a specific goal ("watch for X"), watch for it; otherwise don't proactively ask unless the eval looks weird. Examples worth flagging when relevant: **repetition / "submit loops"** (an agent repeatedly sending the same `submit` *message* instead of calling the `submit` *tool*, so it never submits and burns tokens), unintended shortcut solutions, particular tool-call arguments, signs of reward hacking, or progress toward a stated goal. Watch via `ctl events <task> <sid> --since <cursor> --json`.
  - **Be faithful about confidence.** Some of these you can flag reliably (a literally repeated call); most you can only weakly infer and may lack context to judge. Say so: label low-confidence signals as such, tell the user what you can and can't detect rather than over-claiming, and point them to the sample (TUI) to judge and act.

## Reading results and summarizing
Give the user a **summary**, not raw counts: per-model results, **outliers** (samples far slower or more tokens than the rest), and **flag that errors happened even if retries fixed them**. For **log files** (in-progress or finished), use the **`reading-logs`** skill. Prefer `read_eval_log(..., header_only=True)` and read sample detail selectively; `.eval` logs get large, and reading several at once can exhaust memory.

## `inspect-flow`
If the user already has a Flow spec (a Python file describing an eval-set for [inspect-flow](https://meridianlabs-ai.github.io/inspect_flow/)), launch it with `flow run <path/to/spec.py>`. A Flow spec runs an `eval-set` under the hood, so everything in this skill applies: `ctl tasks` sees the run, all read commands work, and diagnosing stalls and errors is identical. One current caveat: `flow run` doesn't expose `--ctl-server=keep-alive`, so the `ctl` surface vanishes the moment flow exits. Fine for live monitoring; not yet usable for post-completion interrogation.

## Cleanup at end of session
Any process launched with `--ctl-server=keep-alive` parks after the eval finishes and waits **indefinitely** for `inspect ctl release`; it won't exit on its own. Track these yourself: if you launched anything with `--ctl-server=keep-alive` during the session, remember to release it before you wrap up.

For runs you launched: ask the user if they're done interrogating, then release.
```bash
inspect ctl release --pid <pid>
```

For parked runs the user launched themselves: defer entirely. Don't release someone else's parked process unless they ask you to. There's no ownership check today, and `release` silently latches on a still-running eval to "exit when done", which would surprise them.

If you didn't track which launches were keep-alive, you can still spot parked processes in `tasks --json`: an entry with `completed_at` set whose `pid` is still alive (visible in `ps`) is parked. A normal run's entry disappears as soon as the process exits.

## Current limitations
- **No `ctl` write ops.** The write surface today is **`inspect acp`**: it lets a human or an attached agent send a steering message, interrupt generation, cancel a tool call, or cancel a sample, even when the eval was launched headless. Enable on launch with `inspect eval[-set] --acp-server` (off by default). Attach from another shell with `inspect acp` (lists running ACP-enabled evals; pin one via `--task-id` / `--sample-id` / `--epoch`). Full surface: <https://inspect.aisi.org.uk/intervention.html>. This skill stays scoped to `ctl`; reach for ACP when the user wants to delegate the intervention rather than do it in their TUI.
- **`events` is pull-only.** No push, `--follow`, or SSE yet; alerts are bounded by your poll interval (in practice, the time between assistant turns).
- **No decoupled `inspect tui`.** For a detachable human view of an eval *you* launched, use `tmux` + `--display full` (above) or `inspect view start --log-dir <dir>` (a separate viewer; closing it doesn't halt the eval).
