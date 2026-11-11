import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from .store import ProjectError, Store, default_home, identity_from_env
from . import __version__, runtime, onboarding, manager, coordination, setup_flow, teams, collaboration
from .schema import SCHEMA_VERSION, CAPABILITIES

PROTOCOL_VERSION = 1

OPERATIONS = {
    'todo.add': ['requestId', 'id?', 'title', 'sourceRef', 'brief?', 'nextAction?'],
    'todo.promote': ['requestId', 'id', 'brief', 'acceptanceCriteria[]'],
    'item.update': ['requestId', 'id', 'title?', 'brief?', 'nextAction?', 'phase?', 'waitingOn?', 'question?', 'checkpointAt?', 'inputArtifactRefs[]?', 'researchContract?', 'dependencyIds[]?', 'checklist[{title,done}]?'],
    'item.status': ['requestId', 'id', 'status', 'note', 'evidenceRefs[] (required for accepted)'],
    'artifact.add': ['requestId', 'id?', 'workItemId', 'path (external file) OR bundle {root,entrypoint,files[{path,role}],workflow?,claims[]?,external[]?}', 'kind?', 'title?', 'familyId?', 'previousVersionId?', 'version?', 'sourceRef'],
    'artifact.review': ['requestId', 'id', 'status: accepted|rejected|review', 'note'],
    'artifact.disposition': ['requestId', 'id', 'disposition: adopted|deferred|declined', 'note'],
    'artifact.validity': ['requestId', 'id', 'validity: current|stale|superseded', 'supersededBy?', 'note'],
    'artifact.followup': ['requestId', 'id', 'workItemId?', 'title', 'brief? (creates or reuses a todo; never launches it)'],
    'decision.add': ['requestId', 'text', 'sourceRef', 'artifactRefs[]?'],
    'project.update': ['requestId', 'name?', 'goal?', 'stage?', 'summary?'],

    'setup.invite': ['requestId (PM has read the setup Skill and asked whether to begin)'],
    'setup.begin': ['requestId', 'sourceRef (user consent)', 'nextAction?'],
    'setup.defer': ['requestId'],
    'setup.answer': ['requestId', 'key', 'value', 'nextAction'],
    'setup.draft': ['requestId', 'configuration (team-template shape)'],
    'setup.confirm': ['requestId', 'draftRevision', 'sourceRef (specific user confirmation)'],
    'setup.check': ['requestId', 'configurationRevision', 'key', 'status: passed|failed|unverified', 'mode: observed|fixture', 'evidence'],
    'setup.finish': ['requestId (all required capabilities must have observed passing evidence)'],
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
    commands.add_parser('capabilities', help='Inspect local backend installation without calling models or reading secrets')
    template = commands.add_parser('team-template', help='Show a portable team configuration for PM review')
    template.add_argument('--template', choices=teams.TEMPLATES, default='development')
    template.add_argument('--routing', choices=('direct', 'coding-hub'), default='direct')
    template.add_argument('--backend', choices=teams.BACKENDS[:-1], default='pi')
    template.add_argument('--model')
    service = commands.add_parser('service', help='Project-machine deterministic follow-up service')
    service.add_argument('mode', choices=('start', 'run', 'stop', 'status', 'tick'))
    snap = commands.add_parser('snapshot', help='Read panel data bound to an exact terminal/core')
    snap.add_argument('--terminal')
    setup = commands.add_parser('setup', help='Inspect an existing terminal and projects on this machine')
    setup.add_argument('--terminal', required=True)
    bind = commands.add_parser('bind', help='Assign an existing terminal as the unique project Leader')
    for field in ('terminal', 'core-scope', 'project'):
        bind.add_argument('--' + field, required=True)
    for field in ('name', 'goal', 'cwd'):
        bind.add_argument('--' + field)
    bind.add_argument('--replace-generation', type=int, help='Explicitly replace the PM only if this generation still owns the project')
    bind.add_argument('--pm-skill', help='Project machine Skill file/directory; empty selects the bundled Skill')
    bind.add_argument('--worker-backend', choices=manager.BACKENDS, help='Default SubAgent Coding tool')
    bind.add_argument('--worker-model', help='Default SubAgent model; empty uses the Coding tool default')
    notify = commands.add_parser('introduce', help='Send one project introduction to an idle Agent, never force input')
    for field in ('project', 'core-scope'):
        notify.add_argument('--' + field, required=True)
    notify.add_argument('--generation', required=True, type=int)
    for name in ('show', 'context', 'skill', 'history', 'inbox', 'attention', 'collaboration', 'post', 'notify', 'search', 'apply', 'report', 'start', 'worker', 'reconcile', '_run', 'read'):
        sub = commands.add_parser(name)
        sub.add_argument('--project', default=os.environ.get('HERDR_PROJECT_ID'), required=not bool(os.environ.get('HERDR_PROJECT_ID')))
        if name == 'search':
            sub.add_argument('--query', required=True)
        if name == 'collaboration':
            sub.add_argument('--after', type=int, default=0)
            sub.add_argument('--item')
            sub.add_argument('--post')
        if name == 'post':
            sub.add_argument('--notify', action='store_true', help='Deliver once to explicit recipients through hc')
        if name == 'notify':
            sub.add_argument('--post', required=True)
        if name == 'inbox':
            sub.add_argument('--after', type=int, default=0)
            sub.add_argument('--include-handled', action='store_true')
        if name == 'skill':
            source = sub.add_mutually_exclusive_group()
            source.add_argument('--resource', help='Read a complete text resource relative to the configured Skill directory')
            source.add_argument('--list', action='store_true', help='List all files in the configured Skill directory')
            source.add_argument('--setup', action='store_true', help='Activate the bundled PM-led setup Skill, including with a custom PM guide')
        if name in ('apply', 'report', 'post'):
            sub.add_argument('--file', required=True, help='JSON request file, or - for stdin')
        if name in ('apply', 'worker'):
            sub.add_argument('--revision', type=int, required=True)
        if name in ('start', 'worker'):
            sub.add_argument('--backend', choices=manager.BACKENDS, default='pi' if name == 'start' else None)
            sub.add_argument('--model', help='Model for this launch (Worker defaults to project settings)')
            sub.add_argument('--command-json', help='Custom/resume argv array, containing one separate {context} argument')
            sub.add_argument('--space', help='Existing local Herdr Space id; otherwise a project Space is used')
            sub.add_argument('--tab', help='Existing local tab id; otherwise an execution tab is used')
        if name == 'worker':
            sub.add_argument('--item', required=True)
            sub.add_argument('--role', choices=teams.ROLES[1:], default='worker')
            sub.add_argument('--tier', choices=teams.TIERS)
            sub.add_argument('--workflow', choices=('deepresearch', 'autoresearch'))
        if name in ('context', 'reconcile', '_run'):
            sub.add_argument('--run', default=os.environ.get('HERDR_RUN_ID') if name == 'context' else None)
        if name == '_run':
            sub.add_argument('--token', required=True)
        if name == 'read':
            sub.add_argument('--artifact', required=True)
            sub.add_argument('--member', help='Relative member of a published bundle')
            sub.add_argument('--offset', type=int, default=0, help='Byte offset for bounded text reading')
            sub.add_argument('--core-scope', help='Refuse if the connected core changed since the panel snapshot')
            sub.add_argument('--ledger-home', help='Refuse if the selected ledger changed since the panel snapshot')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    store = None
    try:
        if args.action == 'probe':
            result = dict(protocolVersion=PROTOCOL_VERSION, schemaVersion=SCHEMA_VERSION, version=__version__,
                          ledgerHome=str(Path(args.home or default_home()).expanduser().resolve()), capabilities=CAPABILITIES)
        elif args.action == 'capabilities':
            result = dict(backends=teams.capabilities(), roles=teams.ROLE_GUIDANCE)
        elif args.action == 'team-template':
            result = teams.template(args.template, args.routing, args.backend, args.model)
        elif args.action == 'operations':
            result = dict(operations=OPERATIONS,
                          post=['requestId', 'workItemId', 'kind: finding|question|review|reply|assignment|decision', 'text', 'recipients[] (pm or project run ids)', 'artifactRefs[]?', 'replyTo?'],
                          note='apply requires the current Main and project revision; post allows active Workers on their own task. Use post --notify for one hc delivery attempt. No inbox acknowledgements are required.')
        else:
            action = args.action
            scopes = runtime.connected_scopes() if (action == 'snapshot' and args.terminal) or (action == 'read' and args.core_scope) else None
            if action == 'read' and args.core_scope and args.core_scope != scopes[0]:
                raise ProjectError('Connected core changed; refresh the project before reading evidence')
            ledger_home = str(Path(args.home or default_home()).expanduser().resolve())
            if action == 'read' and args.ledger_home and ledger_home != args.ledger_home:
                raise ProjectError('Selected ledger changed; refresh the project before reading evidence')
            store = Store(args.home)
            if action == 'service':
                result = {'start': coordination.service_start, 'run': coordination.service_run,
                          'stop': coordination.service_stop, 'status': coordination.service_status,
                          'tick': coordination.service_tick}[args.mode](store)
            elif action == 'create':
                result = store.create(args.id, args.name, args.goal, args.cwd, args.pm)
            elif action == 'list':
                result = store.snapshot()['projects']
            elif action == 'snapshot':
                result = store.snapshot(args.terminal, scopes=scopes)
                result.update(protocolVersion=PROTOCOL_VERSION, coreScopes=scopes or [], ledgerHome=ledger_home)
            elif action == 'setup':
                result = onboarding.setup(store, args.terminal)
            elif action == 'bind':
                result = onboarding.bind(store, args.terminal, args.core_scope, args.project, args.name, args.goal, args.cwd,
                                         args.replace_generation, args.pm_skill, args.worker_backend, args.worker_model)
            elif action == 'introduce':
                result = onboarding.notify(store, args.project, args.core_scope, args.generation)
            elif action == 'show':
                result = store.public(store.get(args.project))
                result.update(manager.settings(result))
                if result['configuration']['revision']:
                    result['setup']['requiredChecks'] = setup_flow.required_checks(result['configuration'])
            elif action == 'skill':
                project = store.get(args.project)
                if args.setup:
                    print(setup_flow.skill(), end='')
                    return 0
                if args.list:
                    result = dict(path=manager.settings(project)['pmSkill'], resources=manager.list_resources(project))
                else:
                    print(manager.read_skill(project, args.resource), end='')
                    return 0
            elif action == 'context':
                print(runtime.context(store, args.project, args.run))
                return 0
            elif action == 'history':
                result = store.history(args.project)
            elif action == 'inbox':
                result = coordination.inbox(store, args.project, args.after, args.include_handled)
                result['deprecated'] = 'Legacy history only. Use attention for outstanding work; collaboration for records.'
            elif action == 'attention':
                result = collaboration.attention(store.get(args.project))
            elif action == 'collaboration':
                result = collaboration.read(store, args.project, args.after, args.item, args.post)
            elif action == 'post':
                identity = identity_from_env(store)
                result = collaboration.post(store, args.project, read_json(args.file), identity)
                if args.notify:
                    result['delivery'] = collaboration.deliver(store, args.project, result['postId'], identity)
            elif action == 'notify':
                result = collaboration.deliver(store, args.project, args.post, identity_from_env(store))
            elif action == 'search':
                from .artifacts import search
                result = dict(artifacts=search(store.public(store.get(args.project)), args.query))
            elif action == 'apply':
                request = read_json(args.file)
                result = store.apply(args.project, args.revision, request, identity_from_env(store))
                if request.get('op') == 'setup.confirm' and not result.get('replayed') and result['project']['configuration']['followup']['enabled']:
                    try:
                        result['service'] = coordination.service_start(store)
                    except (OSError, ProjectError) as exc:
                        result['service'] = dict(state='unavailable', error=str(exc))
            elif action == 'report':
                request = read_json(args.file)
                if not isinstance(request, dict):
                    raise ProjectError('Report must be an object')
                identity = identity_from_env(store)
                result = store.report(args.project, request, identity)
                if result.get('postId') and not result.get('replayed'):
                    try:
                        result['delivery'] = collaboration.deliver(store, args.project, result['postId'], identity)
                    except (OSError, ProjectError) as exc:
                        result['delivery'] = dict(state='unavailable', error=str(exc))
            elif action in ('start', 'worker'):
                project = store.get(args.project) if action == 'worker' else {}
                profile = teams.resolve(project, args.role, args.backend, args.model, args.tier) if action == 'worker' else None
                if profile and args.command_json:
                    profile['customCommand'] = True
                    profile['fallbackReason'] = None
                    profile['requestedModel'] = profile.get('model')
                    profile['model'] = None
                if action == 'worker' and args.workflow:
                    if args.role != 'research':
                        raise ProjectError('--workflow applies only to Research')
                    profile['workflow'] = args.workflow
                argv = manager.worker_command(project, args.backend, args.model,
                                              json.loads(args.command_json) if args.command_json else None, profile)
                result = runtime.start(store, args.project, argv, args.space, args.tab,
                                       getattr(args, 'item', None), getattr(args, 'revision', None), identity_from_env(store), profile=profile)
            elif action == 'reconcile':
                result = runtime.reconcile(store, args.project, args.run)
            elif action == '_run':
                return runtime.execute(store, args.project, args.token, args.run)
            elif action == 'read':
                result = store.read_artifact(args.project, args.artifact, args.member, args.offset)
                result.update(protocolVersion=PROTOCOL_VERSION, coreScope=scopes[0] if scopes else None, ledgerHome=ledger_home)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ProjectError, OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        if store:
            store.close()
