"""Portable role templates and validated execution preferences (no credentials)."""
import copy
import os
from pathlib import Path
import shutil

from .store import ProjectError, text

BACKENDS = ('pi', 'claude', 'codex', 'opencode', 'feynman')
TIERS = ('breeze', 'flow', 'craft', 'sage', 'apex')
ROLES = ('pm', 'worker', 'explore', 'librarian', 'reviewer', 'research', 'oracle')
TEMPLATES = ('development', 'research', 'mixed')
DEFAULT_TIERS = dict(pm='sage', worker='craft', explore='breeze', librarian='craft', reviewer='craft', oracle='apex')
ROLE_GUIDANCE = {
    'pm': 'Maintain goals, priorities, dependencies, coordination and evidence-based acceptance.',
    'worker': 'Implement only the assigned scope. Verify the result and submit evidence.',
    'explore': 'Read local code, locate symbols and explain call paths. Do not edit repository files.',
    'librarian': 'Inspect official documentation and primary sources. Cite versions and locations. Do not edit repository files.',
    'reviewer': 'Independently compare evidence and changes against acceptance criteria. Report findings; do not edit or merge.',
    'research': 'Investigate the assigned decision, preserve sources, drafts and provenance, and distinguish facts from inference.',
    'oracle': 'Analyze difficult decisions read-only. State evidence, uncertainty and a minimal validation plan.',
}


def executable(backend):
    found = shutil.which(backend)
    if found:
        return found
    # Official OpenCode installer location; background Core shells may omit it.
    if backend == 'opencode':
        candidate = Path.home() / '.opencode/bin/opencode'
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def template(name='development', routing='direct', backend='pi', model=None):
    if name not in TEMPLATES or routing not in ('direct', 'coding-hub') or backend not in BACKENDS[:-1]:
        raise ProjectError('Invalid team template, routing or coding backend')
    enabled = {'pm', 'worker', 'explore', 'librarian', 'reviewer'} if name == 'development' else {'pm', 'research', 'librarian', 'reviewer'}
    if name == 'mixed':
        enabled |= {'worker', 'explore'}
    roles = {}
    for role in ROLES:
        research = role == 'research'
        roles[role] = dict(enabled=role in enabled, backend='feynman' if research else backend,
                           model=None if research else model, tier=DEFAULT_TIERS.get(role),
                           fallback='opencode' if routing == 'coding-hub' and backend == 'pi' and not research else None,
                           isolation='research' if research else 'worktree' if role == 'worker' else 'readonly',
                           workflow='deepresearch' if research else None)
    return dict(template=name, routing=routing, roles=roles, artifactRoot=None, followup=dict(enabled=True))


def validate(value):
    if not isinstance(value, dict):
        raise ProjectError('configuration must be an object')
    unknown = set(value) - {'template', 'routing', 'roles', 'artifactRoot', 'followup'}
    if unknown:
        raise ProjectError('Unknown configuration fields: ' + ', '.join(sorted(unknown)))
    name, routing = value.get('template', 'development'), value.get('routing', 'direct')
    result = template(name, routing)
    roles = value.get('roles', result['roles'])
    if not isinstance(roles, dict) or set(roles) - set(ROLES):
        raise ProjectError('Unknown agent role')
    # Every role has one explicit resolved profile; missing roles inherit the template.
    for role, settings in roles.items():
        allowed = {'enabled', 'backend', 'model', 'tier', 'fallback', 'isolation', 'workflow'}
        if not isinstance(settings, dict) or set(settings) - allowed:
            raise ProjectError(f'Invalid {role} profile')
        selected = result['roles'][role] | settings
        if type(selected['enabled']) is not bool or selected['backend'] not in BACKENDS:
            raise ProjectError(f'Invalid {role} backend or enabled flag')
        if selected['model'] is not None:
            selected['model'] = text(selected['model'], 'model', 300)
        if role == 'research':
            if selected['backend'] != 'feynman' or selected['workflow'] not in ('deepresearch', 'autoresearch') or selected['tier'] is not None or selected['fallback'] is not None:
                raise ProjectError('Research uses Feynman workflows without tier routing or silent fallback')
            if selected['isolation'] != 'research':
                raise ProjectError('Research needs an independent output directory')
        else:
            if selected['backend'] == 'feynman' or selected['tier'] not in TIERS or selected['workflow'] is not None:
                raise ProjectError(f'Invalid coding profile for {role}')
            if role == 'pm' and selected['tier'] not in ('sage', 'apex'):
                raise ProjectError('PM routing uses sage or apex')
            if selected['fallback'] not in (None, 'opencode') or (selected['fallback'] and selected['backend'] != 'pi'):
                raise ProjectError('The supported fallback is Pi to OpenCode')
            if selected['isolation'] not in (('worktree',) if role == 'worker' else ('readonly',)):
                raise ProjectError(f'Invalid workspace strategy for {role}')
        result['roles'][role] = selected
    root = value.get('artifactRoot')
    if root is not None:
        path = Path(text(root, 'artifactRoot')).expanduser()
        if not path.is_absolute():
            raise ProjectError('artifactRoot must be an absolute path on the project machine')
        root = str(path.resolve())
    result['artifactRoot'] = root
    followup = value.get('followup', result['followup'])
    if not isinstance(followup, dict) or set(followup) != {'enabled'} or type(followup['enabled']) is not bool:
        raise ProjectError('followup must contain enabled: true or false')
    result['followup'] = dict(followup)
    if not result['roles']['pm']['enabled']:
        raise ProjectError('A project needs its PM role')
    return result


def resolve(project, role='worker', backend=None, model=None, tier=None):
    if role not in ROLES or role == 'pm':
        raise ProjectError('Choose a SubAgent role; the PM is already bound')
    config = project.get('configuration', {})
    if config.get('revision', 0):
        profile = copy.deepcopy(config['roles'][role])
        if not profile['enabled']:
            raise ProjectError(f'The {role} role is not enabled in this project')
    else:
        legacy = project.get('subAgent') or dict(backend='pi', model=None)
        profile = template('mixed')['roles'][role]
        if role != 'research':
            profile.update(backend=legacy['backend'], model=legacy.get('model'), isolation='worktree' if role == 'worker' else 'readonly')
    # Old saved project-cwd profiles are upgraded at resolution, never in-place
    # on an existing Run. Every new writing execution is isolated.
    if role == 'worker':
        profile['isolation'] = 'worktree'
    if backend:
        if backend not in BACKENDS:
            raise ProjectError('Unknown backend')
        if backend != profile['backend']:
            profile['model'] = None
            profile['fallback'] = None
        profile['backend'] = backend
    if model is not None:
        profile['model'] = text(model, 'model', 300) if model else None
    if tier:
        if role == 'research' or tier not in TIERS:
            raise ProjectError('Invalid difficulty override')
        profile['tier'] = tier
    if (role == 'research') != (profile['backend'] == 'feynman'):
        raise ProjectError('Feynman is the Research backend; coding roles use coding backends')
    # The only automatic fallback happens BEFORE any process has been launched.
    requested_backend = profile['backend']
    fallback_reason = None
    if not executable(requested_backend) and profile.get('fallback') and executable(profile['fallback']):
        profile['backend'] = profile['fallback']
        profile['model'] = None
        fallback_reason = f'{requested_backend} is not installed; using configured fallback'
    if config.get('routing') == 'coding-hub' and role != 'research' and model is None:
        prefix = {'pi': 'remote-magpie/', 'opencode': 'magpie/remote-magpie/'}.get(profile['backend'])
        if not prefix:
            raise ProjectError('Coding Hub group routing needs Pi or OpenCode; choose direct routing for this backend')
        profile['model'] = prefix + 'group/' + profile['tier']
    return dict(profile, role=role, requestedBackend=requested_backend, fallbackReason=fallback_reason,
                configurationRevision=config.get('revision', 0), actualModel=None)


def capabilities():
    # No model calls or reading credentials. Unknown stays unknown until checked.
    return [dict(id=backend, installed=bool(executable(backend)), executable=executable(backend),
                 authentication='unverified', model='unverified', reporting='unverified',
                 researchSearch='unverified' if backend == 'feynman' else 'not-applicable') for backend in BACKENDS]
