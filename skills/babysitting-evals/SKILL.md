---
name: babysitting-evals
description: >-
  Use for monitoring and diagnosing RUNNING Inspect AI evaluations via the
  `inspect ctl` command-line control channel. Triggers when: watching a live
  eval for stalls/errors/retry failures, checking progress of an active eval
  process, launching an eval you'll monitor in parallel, or finding problematic
  samples in a running eval. Does NOT apply to: writing new eval tasks or
  scoring logic, refactoring existing eval tasks, fixing code bugs unrelated to
  live eval monitoring, or analyzing completed eval logs.
---

# Babysitting Inspect evals via the control channel

Every running `inspect eval` process binds a local control endpoint; `inspect ctl`
talks to it so you can observe live evals from a separate shell.

> **In-progress feature — expect gaps.** The control channel is **read-only**: you
> observe via `ctl` and `release` finished processes, but you can't mutate a running
> eval through it. What changing a running eval is *actually* possible today:
> - **Cancel an individual sample or task** — a **human**, from the eval's **TUI**.
> - **Stop the whole eval/process** — the human (Ctrl+C) **or you**
>   (`kill -INT <pid>`, after confirming with the user — same graceful path as Ctrl+C;
>   completed samples are scored and the log finalizes as `cancelled`. Don't use plain
>   `kill` / SIGTERM, Inspect has no handler for it and unflushed samples are lost).
>
> So: spot the problem, then either hand the per-sample/task **cancel** to the human
> (TUI), or — if the whole run is clearly bad — **stop it yourself** (`kill -INT <pid>`),
> fix/adjust, and relaunch.

> **Use the tool's own docs — don't trust this file for the surface.** The exact
> commands, flags, and output shapes live in `inspect ctl --help`, each subcommand's
> `--help` (e.g. `inspect ctl events --help`), and the Inspect docs. Run them to
> learn/confirm the surface; it evolves. This skill is the *workflow and judgment*.

## Quick loop (the common path)
1. `inspect ctl ls` — find running evals (note `task_id`). Add `--json` if you also need `pid` / `log_location` (those are not in the human table).
2. `inspect ctl samples <task>` — per-sample status/progress; repeat to track.
3. On trouble: `inspect ctl sample <task> <sid>` (errors) or `ctl events <task> <sid>`
   (what it's doing).
4. Can't fix via `ctl` → **hand off**: point the human at the sample in the TUI to
   cancel, or stop the run (`kill -INT <pid>`, with their OK — same path as Ctrl+C).
   Details below.

## The surface, briefly (confirm details with `--help`)
Read-only commands today: `ls`, `samples`, `sample`, `errors`, `events`, `release`.
- `ls` — running evals (status, counts, pid, `log_location`). `samples` — per-sample
  table (status / retries / score / time / tokens / `idle` since last activity);
  `--json` carries the raw `last_activity_at` timestamp for delta math;
  `--active-since <ts>` gives a "what changed since I last looked" delta.
- `sample` — one sample's full attempt history (every retry, the final error).
- `errors` — task-wide list of every sample that errored or was retried. The natural first call when babysitting ("did anything go wrong?").
- `events` — **a running sample's transcript events** (`model`/`tool`/`error`/`score`)
  via cursored pull. The way to see *what a sample is actually doing*.
- `release` — free a finished `--keep-alive` process. Does NOT cancel anything.

The human tables are summaries; **`--json` carries the full fields** (`pid`,
`log_location`, `last_activity_at`, event count) — use it for scripting and
stall-detection.

> **Read-only today.** `inspect ctl --help` says this plainly (read-only except
> `release`) — trust it; never claim to have cancelled/throttled an eval via `ctl`.
> What *is* possible to change a running eval is in the top note.

## Use case: you babysit, the human acts
`ctl` can't change a running eval, so the loop is **observe → diagnose → hand off**:
when you find a problem (stall, error storm, retry-exhausted sample, runaway loop),
tell the user **which task and sample** (id + epoch) and **what you saw**, then hand
off (cancel in the TUI, or stop the run — see top note). You surface; they act.

This only works if **someone has the TUI** — which drives the launch decision below.

## Who launched it — the exact difference
`ctl` works the same during the run either way; what differs is **two launch flags**,
which decide who (if anyone) can intervene and whether the surface survives completion:

| | **User-launched** (interactively) | **You-launched** |
|---|---|---|
| Display / TUI | usually default `--display full` → **the human has a TUI and can cancel a sample/task** | you choose: `--display none` → **no TUI, nobody can cancel a sample/task**; or `tmux` + `--display full` → human can attach & cancel |
| `--keep-alive` | often **omitted** → `ctl` surface (+ `release`) **vanishes when the eval finishes** | you should **add it** → eval stays inspectable + `release`-able after it finishes |
| Do you know the config? | no — get `log_location` from `ctl ls`, infer keep-alive behaviorally, or ask | yes — you picked `--log-dir` / keep-alive / display |
| Stop the whole run | the human (Ctrl+C) | you (`kill -INT <pid>`, with their OK) |

Takeaway: a **user-launched** run usually already has a TUI (hand per-sample cancels
to them) but may lack `--keep-alive`; when **you** launch, default to `--keep-alive`
and add `tmux` + `--display full` if the user may want to cancel a sample.

## Use case: the user asks you to BOTH launch and babysit
Headless = no TUI = no one can cancel a sample/task (see the table). So before
launching, **ask (AskUserQuestion) whether to preserve TUI access** — explaining that
per-sample/task cancellation is only possible from the eval's TUI.

If they want it, launch inside a **detached `tmux` session running the full TUI**:
```bash
# If tmux isn't installed, install it first:
#   macOS: brew install tmux   ·   Debian/Ubuntu: sudo apt-get install -y tmux
tmux new-session -d -s eval_<name> \
  '<path>/inspect eval-set <file.py@task> --model <m> --display full --keep-alive --log-dir <dir>'
# tell the user:  tmux attach -t eval_<name>     (detach again with Ctrl-b then d)
```
Default to **`inspect eval-set`** (not `inspect eval`) — more robust retry / recovery /
resume; `--keep-alive` works the same (`--log-dir` is required — it's the resume key).
The full TUI renders in the detached session and you keep monitoring via `ctl` in
parallel; from it the user can cancel an individual sample or task. Install `tmux`
yourself if it's missing.

> **Tmux management is fallible (yours and theirs).** Across a long babysitting
> session you can easily lose track of a detached tmux session, and the user's
> escape hatches matter. After launch, **surface the session name and these commands
> to the user** so they can manage it independently:
> - `tmux ls` — list running sessions.
> - `tmux capture-pane -t eval_<name> -p` — read pane contents without attaching.
>   Use this yourself when you want to peek; `attach` blocks on non-TTY shells.
> - `tmux attach -t eval_<name>` — interact (detach with Ctrl-b then d).
> - `tmux kill-session -t eval_<name>` — force-clean a stuck or orphaned session.
>
> Before launch, check `tmux has-session -t eval_<name>` to avoid name collisions on
> reruns, and after launch give Inspect a few seconds to bind the control endpoint
> before declaring "nothing running" from `ctl ls`. If the user is already inside
> tmux, the nested behavior can confuse both of you; suggest they detach from their
> outer session first.

If TUI access isn't wanted, launch headless (`--display none`) — then per-sample/task
cancellation isn't possible (needs the TUI), though you can still stop the whole run
(`kill -INT <pid>`, confirm first). Don't imply the run can't be stopped.

### Confirm launch choices first — batch the questions
Ask only what the user didn't specify, in **one** AskUserQuestion (≤4), drawing from:
**sample limit** (`--limit`) · **error handling** (resume-durable `--continue-on-fail`
— keep going, mark log `error`, retryable/reusable on resume — vs fail-fast) ·
**per-sample cap** (`--token-limit`/`--time-limit`/`--working-limit`) · **update
cadence + immediate-alert preference**. Confirm `--log-dir`, `--epochs`, model(s)
inline; if you proceed on defaults, state what you chose. **A matrix (models × tasks ×
conditions) → `inspect eval-set`** (one call, many tasks), **not `inspect-flow`** today
(see flow note). **Always `--keep-alive`** for a launch you'll monitor, and **record
the exact command** somewhere for repeatability.

## Use case: monitoring a run the USER started
**Monitor it with `ctl`, exactly like any other running eval — this, not log-scraping,
is how you watch a live eval.** `ctl ls` sees the user's run (the control server binds
by default, regardless of `--display` or `--keep-alive`, so it coexists with their
TUI), and `samples` / `sample` / `errors` / `events` all work while it runs.
Disambiguate by `task_id` if several are running.

Two things to settle up front:
1. **`--keep-alive`** matters only *after* completion (see the table): with it the run
   stays in `ctl ls` and is `release`-able; without it the process exits when the eval
   ends and the `ctl` surface vanishes. There's no keep-alive field — infer from
   whether it lingers after finishing, or ask the user (you can't add it retroactively).
2. **The log dir** — `ctl ls --json` gives each eval's `log_location`, so you can find
   results of a run you didn't launch (no need to ask). For *reading* those logs (works
   in-progress too), use the **`reading-logs`** skill — that's for results/detail, not
   live monitoring (which is `ctl`).

You can monitor/diagnose but **shouldn't** `release` their run (there's no ownership
check today, but releasing a still-running eval is a no-op anyway — parking only
happens post-completion). You **can't** cancel via `ctl` (read-only). If you find an
issue, point them at the sample in their TUI.

## Diagnosing issues
- **Stalls** — judge by **`last_activity_at` deltas across ≥2 polls** (not a single
  snapshot, and NOT `total_tokens`/`message_count`, which sit at 0/1 during a long
  generation). **Idle ≠ stall.** `last_activity_at` advances only when an event is
  emitted, so a single in-flight call (model generation with extended thinking, a
  sandbox `exec`, a slow tool) can legitimately leave it frozen with no new
  `events --since <cursor>` for minutes at a time. Calibrate the window to the task:
  quick QA samples are suspicious at 30s; agentic / sandboxed / extended-thinking
  samples can routinely go 5–10 minutes between events. Also check **what the last
  event was** — a ModelEvent in flight means the model is generating; a SandboxEvent
  in flight means a command is running; a tool call waiting on its return means a
  tool/network call is outstanding. Each implies a different "is this normal"
  threshold. Alert only after corroborating across a calibrated window AND looking at
  the last event type; don't hardcode the poll interval.
- **Errors / retry-exhaustion** — `errors` for the triage list; `sample <task> <sid>`
  for the full attempt history + final error; `events --type error,model` to see *what
  led to* the failure. When a sample errors after exhausting retries, notify
  immediately with the **exact error message** and a short **analysis** (likely cause;
  input-specific vs task-wide). Note: a retried-then-passed sample (`status: completed`,
  `retries>0`) is a success — but still surface that it erred.
- **User-defined event-stream watches** — `ctl events` lets you watch *what a sample is
  doing*, so **ask the user whether there's anything specific they want monitored**.
  Examples: **repetition / "submit loops"** (an agent repeatedly sending the same
  `submit` *message* instead of calling the `submit` *tool*, so it never submits and
  burns tokens), unintended/shortcut solutions, particular tool-call arguments, signs
  of reward hacking, or progress toward a stated goal. Watch via `ctl events <task>
  <sid> --type ... --since <cursor>`.
  - **Be faithful about confidence.** Some of these you can flag reliably (a literally
    repeated call); most you can only weakly infer and may lack context to judge. Say
    so — label low-confidence signals as such, tell the user what you can and can't
    detect rather than over-claiming, and point them to the sample (TUI) to judge/act.

## Inspecting what a sample is doing — `events` (the incremental loop)
`events` is cursored pull: each call returns `{events, next, done, missed}`. Page
forward by passing the prior `next` back via `--since` (only new events); `--tail N`
to peek at the latest, `--type` to filter, `--full` for raw. Watch the envelope:
`done` = sample terminal, `missed > 0` = events were evicted (you have a gap). See
`inspect ctl events --help` for the rest. (Push/`--follow`/SSE isn't shipped yet —
pull-only, so "immediate" means "within your poll interval".)

## Reading results & summarizing
Give the user a **summary**, not raw counts: per-model results, **outliers** (samples
far slower / more tokens than the rest), and **flag that errors happened even if
retries fixed them**. For **log files** (in-progress or finished), use the
**`reading-logs`** skill — prefer `read_eval_log(..., header_only=True)` and read
sample detail selectively (`.eval` logs get large; reading several at once can exhaust
memory).

## Release / cleanup
`inspect ctl release` (or `--pid` when several are parked); finish with `ls` empty.
When you only mean to free a *finished* parked process, use `release` (the clean exit)
— not `kill`. (`kill -INT <pid>` is for deliberately *stopping a bad run*, with the
user's OK — Inspect handles SIGINT as a graceful cancellation, scoring completed
samples and finalizing the log as `cancelled`. Plain `kill` / SIGTERM has no handler,
so unflushed samples are lost and the log may not finalize.)

## `inspect-flow`
**Don't use `inspect-flow` for control-channel babysitting today.** `flow run` has no
`--keep-alive` flag, so its control surface vanishes the moment flow exits and you
can't keep it inspectable. (A flow run *is* visible in `ctl ls` while live — the
in-process launcher binds the server — but you can't park it.) For matrices, use
**`inspect eval-set`**. Revisit if/when flow gains `--keep-alive` / control-channel
integration.

## What the control channel can't do yet (set expectations)
- **No `ctl` write ops** — can't change a running eval via `ctl` (see the top note for
  what *is* possible).
- **`events` is pull-only** — no push/`--follow`/SSE yet (alerts are poll-bounded).
- **No decoupled `inspect tui`** — for a detachable human view of an eval *you*
  launched, use `tmux` + `--display full` (above) or `inspect view start --log-dir
  <dir>` (a separate viewer; closing it doesn't halt the eval).

Tell the user plainly when they ask for something not yet available.