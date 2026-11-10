# Changelog

## 0.2.0

- Project records, evidence, Main and Workers stay on the project's machine. The desktop panel reads them through Herdr's existing machine connection.
- Add `--runtime-only` installation for servers and per-machine discovery/configuration of runtime paths.
- Route remote terminal navigation, session status and cross-machine peeks by the focused terminal's machine.
- Use the target Core's persistent identity for new executions. Guard evidence reads against a changed Core or ledger, and reject ambiguous legacy bindings.
- Preserve explicitly marked last-known records while disconnected; reconnect without creating a replacement Main or a local copy of the ledger.
- Add remote protocol, installer and UI regression tests plus an isolated native Core-machine integration script. SSH between physical hosts and macOS windows remain unverified.

## 0.1.0

- Initial native Project sidebar, durable local ledger, one Main identity per project, managed Workers, evidence review, recovery and standalone installer.
