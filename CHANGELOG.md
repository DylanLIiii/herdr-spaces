# Changelog

## 0.4.1

- Launch Workers as real Herdr Core children with native lifecycle notifications; retain explicit outlive-parent behavior for PM handoff and use native Agent navigation.
- Preserve OpenCode mini and report its actual session/permission/form events through a run-scoped OSC 7501 adapter. Discover the official OpenCode binary when the background PATH omits it.
- Replace routine PM inbox acknowledgements with business attention and task-linked collaboration records. Deliver directly through hc, support in-scope peer review/feedback, and retain old inbox history without replay.
- Separate current executions from prior attempts in the native UI; expose collaboration evidence and accurate unreported status.
- Migrate additively to schema 3 and package the native status adapter. Existing running terminals remain untouched; Core cannot reparent them through a public API.

## 0.4.0

- Add transactional schema-2 migration and a durable PM inbox with structured reports, explicit acknowledgement/handling, checkpoint events and safe recovery from uncertain PTY sends.
- Add an optional project-machine follow-up service, with process locking, deferred delivery to busy PMs, restart recovery and explicit service status.
- Move first-use configuration to the designated PM through the bundled `herdr-spaces-setup` Skill. Ask whether to begin; persist consent, answers, drafts, confirmations and capability evidence across deferral and handoff.
- Add portable development/research/mixed role templates, direct or Coding Hub routing, OpenCode/Feynman launch adapters, immutable Run preferences, Worker worktrees and independent research directories.
- Publish durable, versioned research bundles with manifests, source locators, process files and provenance. Separate report review, recommendation adoption and validity; link decisions and follow-up tasks to exact versions.
- Add native setup progress, separate human/PM attention, artifact search, member/version navigation and an expanded research reader. Preserve native terminals and project-machine ownership.
- Extend runtime bundles and remote upgrade capability checks; add deterministic lifecycle integration and regression coverage.

### Earlier unreleased changes included

- Support explicit PM rebinding with generation checks. Preserve the stable Main identity, project records and active Workers while revoking the previous PM credentials and terminal binding.
- Bundle a complete Project Manager Skill and SubAgent guide, allow a project-specific Skill path, and expose full entry/resource reads through the project CLI.
- Guide SubAgent Coding tool and model selection in the native setup form; apply saved preferences to Worker launches with optional per-launch overrides.
- Upgrade remote runtimes lacking PM configuration support while preserving their registered ledger paths.
- Group native PM setup into project, Skill and SubAgent sections, show tool availability, add a sidebar configuration entry, and use a dedicated handoff confirmation with cancellation. Show saved settings and next steps after success; retry introduction failures without rebinding.
- Launch Codex Workers with `--no-daemon` so each process retains its own Herdr terminal identity.
- Adapt BoardUI-inspired information hierarchy to native GPUI: project summary counts, attention filtering, priority task groups, compact detail views, PM/Worker role badges, and settings summaries with on-demand editing. Preserve the existing personal layout and real ledger/execution state distinctions.

## 0.3.1

- Fix Leader setup failing with `No such file or directory: 'hc'` when the project's background environment omits the user install directory from PATH. Discover Herdr Core from PATH, `HC_INSTALL_DIR`, or `~/.local/bin`, including installations without the optional `hc` alias; validate its version before use.
- Upgrade existing 0.3.0 project runtimes during Leader setup instead of reusing their PATH-dependent implementation. Preserve the registered ledger directory and existing files.
- Add `--remote-name` to retain the remote registration when installing a new personal desktop layout. No Core restart or shell configuration change is required.

## 0.3.0

- Right-click an existing Agent to designate it as Project Leader, then choose or create a project in a native form. The original terminal and session stay in place.
- Prepare a missing project-machine runtime from the desktop's bundled code during setup. First-use empty states offer an action instead of raw installation errors and shell commands.
- Show a Leader label in the personal Agents list; open the existing Leader when a project already has one.
- Send one visible project introduction only to an idle Agent using Core's guarded send. Busy/blocked/shell terminals receive no input; uncertain delivery is never retried automatically.
- Resolve attached Leader CLI credentials from its explicit Core/terminal binding, while retaining token validation for managed executions.

## 0.2.0

- Project records, evidence, Main and Workers stay on the project's machine. The desktop panel reads them through Herdr's existing machine connection.
- Add `--runtime-only` installation for servers and per-machine discovery/configuration of runtime paths.
- Route remote terminal navigation, session status and cross-machine peeks by the focused terminal's machine.
- Use the target Core's persistent identity for new executions. Guard evidence reads against a changed Core or ledger, and reject ambiguous legacy bindings.
- Preserve explicitly marked last-known records while disconnected; reconnect without creating a replacement Main or a local copy of the ledger.
- Add remote protocol, installer and UI regression tests plus an isolated native Core-machine integration script. SSH between physical hosts and macOS windows remain unverified.

## 0.1.0

- Initial native Project sidebar, durable local ledger, one Main identity per project, managed Workers, evidence review, recovery and standalone installer.
