# Native Core integration (0.4.4)

## Responsibility and observed defect

Herdr Core 0.1.19 owns terminal creation, parent/child relationships, OSC 7501 program status, `hc send`, `hc wait`, safe draft/dialog handling and parent notifications for blocked/error/exit. Herdr App owns focusing/peeking at native terminals. Spaces owns goals, tasks, dependencies, questions, decisions and versioned evidence.

On ts-mini, the original t7–t10 execution records were live with `parent: null`, `reported: false`, `status: null`. The previous launcher explicitly used `--no-parent --no-notify` and assigned a separate tab. OpenCode 2.2.7 mini does not invoke the full TUI's program-status reporter. The Python wrapper is not evidence of failure: it preserves the PTY and process lock, but it cannot infer an Agent's state.

Worker launches now use `hc run --parent <actual-pm-terminal> --outlive-parent`, with native parent notifications enabled. They inherit the PM's native group without forcing a new tab; explicit placement remains supported. `--outlive-parent` is deliberate: a PM handoff or close must not kill authorized work. Core records the original parent; Spaces records the current project owner. Core has no supported reparent operation, so existing terminals remain unchanged and are marked as legacy independent executions. No Core database is edited.

OpenCode mini stays enabled. A per-run V2 plugin subscribes to native session events and emits OSC 7501 into that run's own terminal. It tracks only the named session and its descendants, including permission/question blockers. Private server configuration is merged only into the launched process environment. Other backends retain their own reporting. The plugin does not interpret model tokens, screen text, heartbeat frequency, task status or process existence as activity.

## Messages and project memory

`hc send` is the transport for messages and steering; `hc wait` is the wait primitive. Workers and reviewers may directly exchange in-scope feedback. They still cannot change scope, dispatch additional agents or accept project work.

A `post` is a lightweight project record: author, task, kind, text, optional explicit run recipients, artifact version references and reply target. It has no read/handled state. `post --notify` uses hc once; normal short exchanges can use hc directly without being logged again. Reports, assignments and acceptance decisions create linked records. Plain progress does not broadcast.

`attention` derives work from open questions, blocked/review tasks and unreviewed artifacts. A PM successor reads these facts and the relevant collaboration history. No per-message `inbox.acknowledge` / `inbox.handle` is required. The old inbox table, reports and their receipts remain queryable via the deprecated `inbox` command; migration does not delete them or replay them.

Delivery records contain only the attempt/result needed to diagnose missing messages. A reserved send is `uncertain` before I/O; a process crash or timeout cannot cause automatic re-send. A blocked/unreported recipient is marked unavailable without typing into its terminal. A later explicit follow-up or direct hc send follows inspection of the actual recipient; the task's business state remains the recovery source. Delivery does not mean acceptance. The checkpoint service only handles due checkpoints, not lifecycle or generic message scheduling.

## Interfaces

```sh
herdr-project attention --project PROJECT
herdr-project collaboration --project PROJECT --item TASK
herdr-project collaboration --project PROJECT --post POST
herdr-project post --project PROJECT --file POST.json --notify
herdr-project notify --project PROJECT --post POST
herdr-project inbox --project PROJECT --include-handled  # legacy history
hc send TERMINAL "in-scope question or feedback"
hc wait TERMINAL
```

Post fields: `requestId`, `workItemId`, `kind` (finding/question/review/reply; PM may also assignment/decision), `text`, `recipients` (explicit project Run ids or `pm`), optional `artifactRefs` and `replyTo`. No `@all` broadcast. Active Workers post under their own assignment; peer replies are linked through recipients and replyTo. Only the author or current PM may trigger a recorded delivery. Repeating a post request is idempotent; an existing delivery receipt is returned without sending again.

## Upgrade and verification boundary

Schema 3 adds collaboration and delivery tables; schema 1/2 business records, identity, revision and legacy inbox remain intact. New code accepts old records; old binaries must not open schema 3. Stop only the Spaces checkpoint service before migration; do not stop Agent terminals or shared Core. In-place updates preserve old runtime paths for active wrappers, while new operations use the new schema implementation.

Existing mini processes did not inherit the status adapter and cannot gain a Core parent through a public hot-update API. Do not restart them to manufacture a green status. New runs use the corrected integration. Native UI describes unreported status accurately and opens live terminals through `agent.focus`; previous attempts are separated from current owners.

Sources: https://herdr.dev/core/#agents ; https://github.com/herdrdev/herdr-core/blob/main/docs/commands.md ; OpenCode v2.2.7 `packages/tui/src/context/program-status.ts`, `packages/schema/src/session-status-event.ts`, `packages/plugin/src/promise/plugin.ts`. Antigravity https://antigravity.google/docs/swarm/ informed the distinction between shared collaboration records and directed wakeups; its transport/runtime is not copied.

## Audit follow-up in 0.4.2

Every new writing Worker requires an isolated Git worktree. Old project-cwd preferences are resolved to worktree for the next launch without mutating existing Runs; configuration validation and the lower-level launch/preparation guard both reject unisolated writing. A repository without a usable HEAD reports a preparation failure instead of falling back to the shared directory.

The OpenCode event subscription clears OSC status on normal exhaustion, failure and teardown. Late snapshots cannot revive a closed subscription. Four setup-level lifecycle tests reproduce the original failures and verify the correction.

`production_mini_smoke.py` runs the exact production manager/start/_run/standalone-mini chain against a loopback deterministic HTTP model. It observes Core parent linkage and working/done/error transitions; no paid provider receives requests. Permission/question mappings remain covered by native-event tests rather than claimed as end-to-end model interaction. See `docs/native-core-audit/production-mini.json`. Original v0.4.0 parent failure and status lifecycle failure logs are retained in that directory. Actual ts-mini before/after snapshots are allowlisted, retaining identities, Run/report ids, artifact ids and Core states without credentials or prompts.

## Snapshot recovery in 0.4.3

Absent or invalid activity timestamps no longer imply idle. A snapshot needs actual activity/completion evidence; otherwise the adapter clears status. During bootstrap it buffers native state/blocker events, independently loads session and permission snapshots, and replays the buffered events before emitting any safe input state. Thus a busy event cannot discard an existing permission wait, and a reply arriving during the snapshot removes that stale permission. If permission inspection fails, an existing session cannot be advertised idle/working; an explicit newly-created session event can establish a fresh event-only session. Buffering is bounded and closes the observer if exceeded. Stream end/failure still clears and fences late snapshots.

`tests/native-status-recovery.test.js` covers missing/invalid timestamps, concurrent busy + pending permission, replied permission versus stale snapshot, question versus idle snapshot, failed inspection and fresh session creation. Before/after evidence is under `docs/native-core-audit/recovery-*.txt`. The exact production launch is rechecked against the deterministic loopback model in `production-mini-recovery.json`; it does not imply live-model research or exhaustive backend support.

## Actual project and native blocker acceptance (0.4.4)

The actual deployed target is **ts-mini / opencode-antigravity-bridge**, project `project-e9d5e3b56bea4b38`. Its new Run `run-e256ea38c5ae48e7` executes in `t13`, with Core parent `ts-mini/t1`, native notifications enabled, and observed `working / opencode`. `docs/native-core-audit/opencode-antigravity-actual-effect.json` is collected from this project, not from the loopback fixture. The actual project screenshot shows its name, current execution, parent and truthful legacy status.

The native child is opened with `terminal.peek`, matching Herdr's native Agents-list action. On the current installed layout, `agent.focus` alone did not expose the child; that negative observation is retained in `agent-focus-before.json`, and the successful native overlay is recorded in `actual-project-peek.json` and the cropped child-window header. Independent terminals and the PM keep `agent.focus`.

`blocker_mini_smoke.py` uses the exact production mini chain and sends deterministic loopback model tool calls to **actual OpenCode shell and question tools**. The shell tool creates a real permission request; question creates a real form. Core observes `blocked/kind=permission` and `blocked/kind=question`. Neither event is manually injected, and no approval or answer is supplied. `blocking-mini.json` records these real Agent/tool event outcomes with zero paid calls.

Current installation is 0.4.4. `current-installed-inventory.json` lists every active local Spaces module and runtime file hash; the actual target JSON lists remote runtime hashes. `final-installations.json` records backups and zero Agent restarts. Older 0.4.2/0.4.3 records are explicitly historical; empty updatedMods in those receipts meant runtime-only changes, not a missing UI installation.
