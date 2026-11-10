# Changelog

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
