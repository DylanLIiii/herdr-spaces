import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from .store import ProjectError, Store, default_home, identity_from_env
from . import __version__, runtime, onboarding

PROTOCOL_VERSION = 1

OPERATIONS = {
    'todo.add': ['requestId', 'id?', 'title', 'sourceRef', 'brief?', 'nextAction?'],
    'todo.promote': ['requestId', 'id', 'brief', 'acceptanceCriteria[]'],
    'item.update': ['requestId', 'id', 'title?', 'brief?', 'nextAction?', 'dependencyIds[]?', 'checklist[{title,done}]?'],
    'item.status': ['requestId', 'id', 'status', 'note', 'evidenceRefs[] (required for accepted)'],
    'artifact.add': ['requestId', 'id?', 'workItemId', 'path (existing absolute file)', 'title?', 'version?', 'sourceRef'],
    'artifact.review': ['requestId', 'id', 'status: accepted|rejected|review', 'note'],
    'decision.add': ['requestId', 'text', 'sourceRef'],
    'project.update': ['requestId', 'name?', 'goal?'],
}


def read_json(path):
    if path == '-':
        raw = sys.stdin.read(1048577)
    else:
        with Path(path).open() as source:
            raw = source.read(1048577)
    if len(raw) > 1048576:
        raise ProjectError('Request too large (limit 1 MiB)')
    return json.loads(raw)


def parser():
    p = argparse.ArgumentParser(prog='herdr-project', description='Persistent projects beside native Herdr terminals')
    p.add_argument('--home', help='Data directory (default: HERDR_PROJECTS_HOME / XDG data)')
    commands = p.add_subparsers(dest='action', required=True)
    create = commands.add_parser('create', help='Create a durable project and one stable Main identity')
    create.add_argument('id')
    for field in ('name', 'goal', 'cwd'):
        create.add_argument('--' + field, required=True)
    create.add_argument('--pm', help='Explicit existing pm.md to link; never overwritten')
    commands.add_parser('list')
    commands.add_parser('probe', help='Describe this machine\'s installed runtime without creating a ledger')
    commands.add_parser('operations', help='Describe JSON write operations')
    snap = commands.add_parser('snapshot', help='Read panel data bound to an exact terminal/core')
    snap.add_argument('--terminal')
    setup = commands.add_parser('setup', help='Inspect an existing terminal and projects on this machine')
    setup.add_argument('--terminal', required=True)
    bind = commands.add_parser('bind', help='Assign an existing terminal as the unique project Leader')
    for field in ('terminal', 'core-scope', 'project'):
        bind.add_argument('--' + field, required=True)
    for field in ('name', 'goal', 'cwd'):
        bind.add_argument('--' + field)
    notify = commands.add_parser('introduce', help='Send one project introduction to an idle Agent, never force input')
    for field in ('project', 'core-scope'):
        notify.add_argument('--' + field, required=True)
    notify.add_argument('--generation', required=True, type=int)
    for name in ('show', 'context', 'history', 'apply', 'report', 'start', 'worker', 'reconcile', '_run', 'read'):
        sub = commands.add_parser(name)
        sub.add_argument('--project', default=os.environ.get('HERDR_PROJECT_ID'), required=not bool(os.environ.get('HERDR_PROJECT_ID')))
        if name in ('apply', 'report'):
            sub.add_argument('--file', required=True, help='JSON request file, or - for stdin')
        if name in ('apply', 'worker'):
            sub.add_argument('--revision', type=int, required=True)
        if name in ('start', 'worker'):
            sub.add_argument('--backend', choices=('pi', 'claude', 'codex'), default='pi')
            sub.add_argument('--command-json', help='Custom/resume argv array, containing one separate {context} argument')
            sub.add_argument('--space', help='Existing local Herdr Space id; otherwise a project Space is used')
            sub.add_argument('--tab', help='Existing local tab id; otherwise an execution tab is used')
        if name == 'worker':
            sub.add_argument('--item', required=True)
        if name in ('context', 'reconcile', '_run'):
            sub.add_argument('--run', default=os.environ.get('HERDR_RUN_ID') if name == 'context' else None)
        if name == '_run':
            sub.add_argument('--token', required=True)
        if name == 'read':
            sub.add_argument('--artifact', required=True)
            sub.add_argument('--core-scope', help='Refuse if the connected core changed since the panel snapshot')
            sub.add_argument('--ledger-home', help='Refuse if the selected ledger changed since the panel snapshot')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    store = None
    try:
        if args.action == 'probe':
            result = dict(protocolVersion=PROTOCOL_VERSION, schemaVersion=1, version=__version__,
                          ledgerHome=str(Path(args.home or default_home()).expanduser().resolve()), capabilities=['leader-bind', 'guarded-introduction'])
        elif args.action == 'operations':
            result = dict(operations=OPERATIONS, note='All apply requests require op, requestId and the current project revision. Call from the managed Main terminal. Replaying the same requestId/content is idempotent.')
        else:
            action = args.action
            scopes = runtime.connected_scopes() if (action == 'snapshot' and args.terminal) or (action == 'read' and args.core_scope) else None
            if action == 'read' and args.core_scope and args.core_scope != scopes[0]:
                raise ProjectError('Connected core changed; refresh the project before reading evidence')
            ledger_home = str(Path(args.home or default_home()).expanduser().resolve())
            if action == 'read' and args.ledger_home and ledger_home != args.ledger_home:
                raise ProjectError('Selected ledger changed; refresh the project before reading evidence')
            store = Store(args.home)
            if action == 'create':
                result = store.create(args.id, args.name, args.goal, args.cwd, args.pm)
            elif action == 'list':
                result = store.snapshot()['projects']
            elif action == 'snapshot':
                result = store.snapshot(args.terminal, scopes=scopes)
                result.update(protocolVersion=PROTOCOL_VERSION, coreScopes=scopes or [], ledgerHome=ledger_home)
            elif action == 'setup':
                result = onboarding.setup(store, args.terminal)
            elif action == 'bind':
                result = onboarding.bind(store, args.terminal, args.core_scope, args.project, args.name, args.goal, args.cwd)
            elif action == 'introduce':
                result = onboarding.notify(store, args.project, args.core_scope, args.generation)
            elif action == 'show':
                result = store.public(store.get(args.project))
            elif action == 'context':
                print(runtime.context(store, args.project, args.run))
                return 0
            elif action == 'history':
                result = store.history(args.project)
            elif action == 'apply':
                result = store.apply(args.project, args.revision, read_json(args.file), identity_from_env(store))
            elif action == 'report':
                request = read_json(args.file)
                if not isinstance(request, dict):
                    raise ProjectError('Report must be an object')
                result = store.report(args.project, request, identity_from_env(store))
            elif action in ('start', 'worker'):
                argv = runtime.command(json.loads(args.command_json) if args.command_json else None, args.backend)
                result = runtime.start(store, args.project, argv, args.space, args.tab,
                                       getattr(args, 'item', None), getattr(args, 'revision', None), identity_from_env(store))
            elif action == 'reconcile':
                result = runtime.reconcile(store, args.project, args.run)
            elif action == '_run':
                return runtime.execute(store, args.project, args.token, args.run)
            elif action == 'read':
                result = store.read_artifact(args.project, args.artifact)
                result.update(protocolVersion=PROTOCOL_VERSION, coreScope=scopes[0] if scopes else None, ledgerHome=ledger_home)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ProjectError, OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        if store:
            store.close()
