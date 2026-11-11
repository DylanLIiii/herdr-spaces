"""One writer per checkout; isolated worktrees and durable research directories."""
import hashlib
import json
from pathlib import Path
import subprocess

from .store import ProjectError
from . import manager, teams


def git(cwd, *args):
    try:
        value = subprocess.run(['git', '-C', str(cwd), *args], text=True, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProjectError(f'Workspace git operation failed: {exc}') from exc
    if value.returncode:
        raise ProjectError('Workspace git operation failed: ' + value.stderr[:1500])
    return value.stdout.strip()


def artifact_root(store, project):
    configured = project.get('configuration', {}).get('artifactRoot')
    return Path(configured) if configured else store.home / 'projects' / project['id'] / 'artifacts'


def check_writer(store, project, profile):
    if profile['role'] != 'worker' or profile['isolation'] != 'project':
        return
    cwd = str(Path(project['cwd']).resolve())
    for row in store.db.execute('SELECT body FROM projects'):
        other = json.loads(row[0])
        for run in other['runs']:
            if run['state'] not in ('starting', 'running', 'uncertain'):
                continue
            execution = run.get('execution', {})
            if execution.get('role', 'worker') == 'worker' and str(Path(run.get('cwd', other['cwd'])).resolve()) == cwd:
                raise ProjectError('This checkout already has a live/uncertain writer. Use an isolated worktree or reconcile the existing run.')


def prepare(store, project, run, profile):
    base = store.home / 'projects' / project['id'] / 'runs' / run['id']
    output = artifact_root(store, project) / 'work' / run['id']
    output.mkdir(parents=True, exist_ok=True)
    cwd, branch, commit = Path(project['cwd']), None, None
    if profile['isolation'] == 'worktree':
        commit = git(cwd, 'rev-parse', 'HEAD')
        branch = 'spaces/' + run['id']
        workspace = base / 'checkout'
        workspace.parent.mkdir(parents=True, exist_ok=True)
        if workspace.exists():
            raise ProjectError('Reserved workspace already exists; reconcile rather than overwrite it')
        git(cwd, 'worktree', 'add', '-b', branch, str(workspace), commit)
        cwd = workspace
    elif profile['isolation'] == 'research':
        cwd = output
    else:
        try:
            commit = git(cwd, 'rev-parse', 'HEAD')
        except ProjectError:
            pass
    task = store.item(project, run['workItemId'])
    refs = task.get('inputArtifactRefs', [])
    from .artifacts import verify
    selected = [artifact for artifact in project['artifacts'] if artifact['id'] in refs]
    if len(selected) != len(set(refs)):
        raise ProjectError('A referenced input artifact version is missing')
    for artifact in selected:
        verify(artifact)
    inputs = [{key: artifact.get(key) for key in ('id', 'version', 'sha256', 'path', 'validity')}
              for artifact in selected]
    resources = {name: hashlib.sha256(manager.skill_file(project, name).read_bytes()).hexdigest()
                 for name in manager.list_resources(project)}
    return dict(cwd=str(cwd), branch=branch, baseCommit=commit, outputRoot=str(output),
                execution=dict(profile), inputArtifacts=inputs,
                skillSnapshot=dict(pm=hashlib.sha256(manager.read_skill(project).encode()).hexdigest(), resources=resources,
                                   role=hashlib.sha256(teams.ROLE_GUIDANCE[profile['role']].encode()).hexdigest()))


def research_contract(task, profile):
    if profile['role'] != 'research':
        return
    if profile.get('workflow') != 'autoresearch':
        return
    contract = task.get('researchContract')
    required = ('objective', 'metric', 'unit', 'direction', 'benchmark', 'allowedPaths', 'environment', 'maxIterations', 'userConfirmation')
    if not isinstance(contract, dict) or any(key not in contract for key in required):
        raise ProjectError('Autoresearch needs an explicitly confirmed benchmark contract before launch')
    if contract['direction'] not in ('minimize', 'maximize') or type(contract['maxIterations']) is not int or not 1 <= contract['maxIterations'] <= 10000:
        raise ProjectError('Invalid benchmark direction or iteration bound')
    from .store import text, strings
    for key in ('objective', 'metric', 'unit', 'environment', 'userConfirmation'):
        text(contract[key], key)
    strings(contract['benchmark'], 'benchmark argv', True)
    strings(contract['allowedPaths'], 'allowed paths', True)
