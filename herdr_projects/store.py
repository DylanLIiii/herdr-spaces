"""Transactional project records. Runtime attention is never task acceptance."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid


class ProjectError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return prefix + '-' + uuid.uuid4().hex[:16]


def text(value, label, maximum=10000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ProjectError(f'{label} must be nonempty text (at most {maximum} characters)')
    return value.strip()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', value):
        raise ProjectError('Invalid id')
    return value


def strings(value, label, nonempty=False):
    if not isinstance(value, list) or len(value) > 200 or (nonempty and not value):
        raise ProjectError(f'{label} must be a list' + (' with at least one entry' if nonempty else ''))
    return [text(v, label) for v in value]


def file_hash(path):
    with Path(path).open('rb') as source:
        raw = source.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise ProjectError('Artifact is larger than 10 MiB; register a bounded report instead')
    return hashlib.sha256(raw).hexdigest()


def default_home():
    return Path(os.environ.get('HERDR_PROJECTS_HOME') or Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'herdr-projects')


def core_scope():
    # Never bind a terminal address from a different core instance.
    return os.environ.get('HC_SOCKET') or os.environ.get('HC_SESSION', 'default')


class Store:
    def __init__(self, home=None):
        self.home = Path(home or default_home()).expanduser().resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.home / 'projects.sqlite3', timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            raise ProjectError(f'Unsupported ledger schema {version}; do not downgrade this installation')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, project_id TEXT NOT NULL,
            request_id TEXT NOT NULL, digest TEXT NOT NULL, actor TEXT NOT NULL,
            revision INTEGER NOT NULL, at TEXT NOT NULL, payload TEXT NOT NULL,
            UNIQUE(project_id, request_id));
          CREATE TABLE IF NOT EXISTS bindings(scope TEXT NOT NULL, terminal TEXT NOT NULL,
            project_id TEXT NOT NULL, role TEXT NOT NULL, run_id TEXT,
            PRIMARY KEY(scope, terminal));
          PRAGMA user_version=1;
        ''')

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def get(self, project_id):
        row = self.db.execute('SELECT body FROM projects WHERE id=?', (project_id,)).fetchone()
        if row is None:
            raise ProjectError(f'Unknown project: {project_id}')
        return json.loads(row['body'])

    def save(self, project):
        project['updatedAt'] = now()
        self.db.execute('UPDATE projects SET body=? WHERE id=?', (json.dumps(project, ensure_ascii=False), project['id']))

    def create(self, project_id, name, goal, cwd, pm_path=None):
        identifier(project_id)
        cwd = str(Path(cwd).expanduser().resolve(strict=True))
        if not Path(cwd).is_dir():
            raise ProjectError('cwd must be a directory')
        pm = str(Path(pm_path).expanduser().resolve()) if pm_path else str(self.home / 'projects' / project_id / 'pm.md')
        project = dict(id=project_id, name=text(name, 'name', 200), goal=text(goal, 'goal'), cwd=cwd,
                       pmPath=pm, revision=0, createdAt=now(), updatedAt=now(),
                       main=dict(id=uid('main'), generation=0, state='inactive', terminal=None, scope=None),
                       items=[], runs=[], artifacts=[], decisions=[])
        with self.transaction():
            try:
                self.db.execute('INSERT INTO projects VALUES(?, ?)', (project_id, json.dumps(project, ensure_ascii=False)))
            except sqlite3.IntegrityError as exc:
                raise ProjectError(f'Project already exists: {project_id}') from exc
        # Existing coding-hub narratives are linked explicitly, never overwritten.
        if not pm_path:
            Path(pm).parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(pm, 'x') as f:
                    f.write(f'# {project["name"]}\n\n{project["goal"]}\n\n## 决策与关键路径\n\n任务状态由结构化账本维护。\n')
            except FileExistsError:
                pass
        return self.public(project)

    @staticmethod
    def public(project):
        result = json.loads(json.dumps(project))
        result['main'].pop('token', None)
        for run in result['runs']:
            run.pop('token', None)
        return result

    def snapshot(self, terminal=None, scope=None, scopes=None):
        projects = [self.public(json.loads(r[0])) for r in self.db.execute('SELECT body FROM projects ORDER BY id')]
        candidates = list(dict.fromkeys(scopes or [scope or core_scope()]))
        bindings = [row for candidate in candidates if terminal for row in self.db.execute(
            'SELECT * FROM bindings WHERE scope=? AND terminal=?', (candidate, terminal))]
        if len(bindings) > 1:
            raise ProjectError('Ambiguous legacy terminal binding; inspect the original core/ledger before continuing')
        binding = bindings[0] if bindings else None
        project = next((p for p in projects if binding and p['id'] == binding['project_id']), None)
        return dict(schemaVersion=1, project=project, binding=dict(binding) if binding else None,
                    projects=[{k: p[k] for k in ('id', 'name', 'cwd')} for p in projects])

    def bind(self, project_id, terminal, scope, role, run_id=None):
        row = self.db.execute('SELECT project_id,role,run_id FROM bindings WHERE scope=? AND terminal=?', (scope, terminal)).fetchone()
        if row and (row['project_id'], row['role'], row['run_id']) != (project_id, role, run_id):
            raise ProjectError('Terminal already belongs to a different project or role')
        self.db.execute('INSERT OR IGNORE INTO bindings VALUES(?,?,?,?,?)', (scope, terminal, project_id, role, run_id))

    def check_main(self, project, identity):
        main = project['main']
        if not identity or identity.get('project') != project['id'] or identity.get('role') != 'main' or identity.get('main') != main['id'] or identity.get('generation') != main['generation'] or identity.get('token') != main.get('token') or main['state'] != 'running':
            raise ProjectError('Main identity is missing or stale. Use this project\'s managed Main terminal and reload context.')

    def event(self, p, request_id, digest, actor, payload):
        self.db.execute('INSERT INTO events(project_id,request_id,digest,actor,revision,at,payload) VALUES(?,?,?,?,?,?,?)',
                        (p['id'], request_id, digest, actor, p['revision'], now(), json.dumps(payload, ensure_ascii=False)))

    def replay(self, project_id, request_id, digest):
        row = self.db.execute('SELECT * FROM events WHERE project_id=? AND request_id=?', (project_id, request_id)).fetchone()
        if row and row['digest'] != digest:
            raise ProjectError('requestId was already used for different content')
        return row

    def apply(self, project_id, revision, request, identity):
        if not isinstance(request, dict):
            raise ProjectError('Request must be an object')
        identifier(request.get('requestId'))
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        with self.transaction():
            p = self.get(project_id)
            self.check_main(p, identity)
            if self.replay(project_id, request['requestId'], digest):
                return dict(replayed=True, project=self.public(p))
            if type(revision) is not int or p['revision'] != revision:
                raise ProjectError(f'Revision conflict: expected {revision}, current {p["revision"]}. Reload and review before retrying.')
            self.operation(p, request)
            p['revision'] += 1
            self.save(p)
            self.event(p, request['requestId'], digest, p['main']['id'], request)
            return dict(replayed=False, project=self.public(p))

    @staticmethod
    def item(p, item_id):
        item = next((i for i in p['items'] if i['id'] == item_id), None)
        if item is None:
            raise ProjectError(f'Unknown work item: {item_id}')
        return item

    def operation(self, p, r):
        op = r.get('op')
        if op == 'todo.add':
            for optional in ('brief', 'nextAction'):
                if optional in r and (not isinstance(r[optional], str) or len(r[optional]) > 10000):
                    raise ProjectError(f'{optional} must be text of at most 10000 characters')
            item_id = identifier(r.get('id', uid('work')))
            if any(i['id'] == item_id for i in p['items']):
                raise ProjectError('Work item id already exists')
            p['items'].append(dict(id=item_id, projectId=p['id'], kind='todo', title=text(r.get('title'), 'title', 300),
                                  status='open', sourceRef=text(r.get('sourceRef'), 'sourceRef'), brief=r.get('brief', ''),
                                  nextAction=r.get('nextAction', ''), revision=1, createdAt=now(), updatedAt=now(),
                                  createdBy=p['main']['id'], updatedBy=p['main']['id'], acceptanceCriteria=[],
                                  checklist=[], dependencyIds=[], artifactIds=[], activeRunId=None))
            return
        if op == 'artifact.add':
            self.add_artifact(p, r)
            return
        if op == 'artifact.review':
            a = next((a for a in p['artifacts'] if a['id'] == r.get('id')), None)
            if not a or r.get('status') not in ('accepted', 'rejected', 'review'):
                raise ProjectError('Unknown artifact or invalid review status')
            if r['status'] == 'accepted' and file_hash(a['path']) != a['sha256']:
                raise ProjectError('Artifact changed since registration; register a new version before accepting')
            a.update(status=r['status'], reviewNote=text(r.get('note'), 'review note'), reviewedBy=p['main']['id'])
            return
        if op == 'decision.add':
            p['decisions'].append(dict(id=uid('decision'), text=text(r.get('text'), 'decision'), sourceRef=text(r.get('sourceRef'), 'sourceRef'), at=now()))
            return
        if op == 'project.update':
            if 'goal' in r:
                p['goal'] = text(r['goal'], 'goal')
            if 'name' in r:
                p['name'] = text(r['name'], 'name', 200)
            return
        i = self.item(p, r.get('id'))
        if op == 'todo.promote':
            if i['kind'] != 'todo' or i['status'] != 'open':
                raise ProjectError('Only an open todo can be promoted')
            i.update(kind='task', status='ready', brief=text(r.get('brief'), 'scope'),
                     acceptanceCriteria=strings(r.get('acceptanceCriteria'), 'acceptanceCriteria', True))
        elif op == 'item.update':
            for key in ('title', 'brief', 'nextAction'):
                if key in r:
                    i[key] = text(r[key], key)
            if 'checklist' in r:
                if not isinstance(r['checklist'], list) or len(r['checklist']) > 100:
                    raise ProjectError('Invalid checklist')
                i['checklist'] = [dict(title=text(x.get('title'), 'step'), done=x.get('done') is True) for x in r['checklist'] if isinstance(x, dict)]
                if len(i['checklist']) != len(r['checklist']):
                    raise ProjectError('Invalid checklist entry')
            if 'dependencyIds' in r:
                deps = strings(r['dependencyIds'], 'dependencyIds')
                for dep in deps:
                    self.item(p, dep)
                if i['id'] in deps:
                    raise ProjectError('A task cannot depend on itself')
                i['dependencyIds'] = deps
                self.check_dependencies(p)
        elif op == 'item.status':
            target = r.get('status')
            transitions = {'open': {'resolved', 'cancelled'}, 'ready': {'cancelled'},
                           'running': {'blocked', 'review', 'cancelled'}, 'blocked': {'running', 'review', 'cancelled'},
                           'review': {'accepted', 'ready', 'cancelled'}, 'accepted': {'ready'},
                           'resolved': {'open'}, 'cancelled': {'open' if i['kind'] == 'todo' else 'ready'}}
            if target not in transitions.get(i['status'], set()):
                raise ProjectError(f'Invalid transition: {i["status"]} → {target}')
            note = text(r.get('note'), 'transition reason')
            if target == 'accepted':
                refs = strings(r.get('evidenceRefs'), 'evidenceRefs', True)
                evidence = {a['id']: a for a in p['artifacts'] if a.get('workItemId') == i['id']}
                if any(ref not in evidence or evidence[ref]['status'] != 'accepted' for ref in refs):
                    raise ProjectError('Acceptance needs this task\'s reviewed, accepted artifacts')
                if any(file_hash(evidence[ref]['path']) != evidence[ref]['sha256'] for ref in refs):
                    raise ProjectError('Accepted evidence changed; register and review a new version')
                i['acceptedEvidenceRefs'] = refs
            if target in ('ready', 'cancelled'):
                run = next((x for x in p['runs'] if x['id'] == i['activeRunId']), None)
                if run and run['state'] in ('starting', 'running', 'uncertain'):
                    raise ProjectError('Execution is still live/uncertain. Reconcile it before rescheduling or cancelling.')
                i['activeRunId'] = None
            i.update(status=target, resolution=note)
        else:
            raise ProjectError(f'Unknown operation: {op}')
        i.update(revision=i['revision'] + 1, updatedAt=now(), updatedBy=p['main']['id'])

    def check_dependencies(self, p):
        visiting, visited = set(), set()
        def visit(item):
            if item['id'] in visiting:
                raise ProjectError('Dependency cycle')
            if item['id'] in visited:
                return
            visiting.add(item['id'])
            for dep in item['dependencyIds']:
                visit(self.item(p, dep))
            visiting.remove(item['id'])
            visited.add(item['id'])
        for i in p['items']:
            visit(i)

    def add_artifact(self, p, r, run=None):
        aid = identifier(r.get('id', uid('artifact')))
        if any(a['id'] == aid for a in p['artifacts']):
            raise ProjectError('Artifact id already exists; submit a new version with a new id')
        item = self.item(p, run['workItemId'] if run else r.get('workItemId'))
        candidate = Path(text(r.get('path'), 'artifact path')).expanduser()
        if not candidate.is_absolute():
            raise ProjectError('Artifact path must be absolute')
        location = str(candidate.resolve(strict=True))
        path = Path(location)
        if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            raise ProjectError('Artifact must be a file of at most 10 MiB')
        digest = file_hash(path)
        a = dict(id=aid, title=text(r.get('title', path.name), 'artifact title', 300), path=location,
                 workItemId=item['id'], runId=run['id'] if run else None, version=text(r.get('version', '1'), 'version', 80),
                 status='review', sha256=digest, createdAt=now(), sourceRef=text(r.get('sourceRef', run['id'] if run else ''), 'sourceRef'))
        p['artifacts'].append(a)
        item['artifactIds'].append(aid)
        return a

    def report(self, project_id, request, identity):
        identifier(request.get('requestId'))
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        with self.transaction():
            p = self.get(project_id)
            run = next((x for x in p['runs'] if x['id'] == identity.get('run')), None)
            if identity.get('role') != 'worker' or identity.get('project') != project_id or not run or identity.get('token') != run.get('token'):
                raise ProjectError('Worker identity does not match this run')
            if self.replay(project_id, request['requestId'], digest):
                return dict(replayed=True, project=self.public(p))
            item = self.item(p, run['workItemId'])
            if item['activeRunId'] != run['id'] or run['state'] != 'running' or item['status'] not in ('running', 'blocked', 'review'):
                raise ProjectError('Late report for an inactive run; Main must review it explicitly')
            report = dict(id=request['requestId'], text=text(request.get('text'), 'report'), at=now())
            artifacts = request.get('artifacts', [])
            if not isinstance(artifacts, list) or len(artifacts) > 50:
                raise ProjectError('Invalid report artifacts')
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    raise ProjectError('Artifact must be an object')
                self.add_artifact(p, artifact, run)
            run.setdefault('reports', []).append(report)
            # Worker submission requests review, it cannot accept its own work.
            if request.get('submitted') is True:
                item['status'] = 'review'
            item.update(revision=item['revision'] + 1, updatedAt=now(), updatedBy=run['id'])
            p['revision'] += 1
            self.save(p)
            self.event(p, request['requestId'], digest, run['id'], request)
            return dict(replayed=False, project=self.public(p))

    def history(self, project_id):
        self.get(project_id)
        return [dict(r) | {'payload': json.loads(r['payload'])} for r in self.db.execute(
            'SELECT seq,request_id,actor,revision,at,payload FROM events WHERE project_id=? ORDER BY seq DESC LIMIT 100', (project_id,))]

    def read_artifact(self, project_id, artifact_id):
        p = self.get(project_id)
        if artifact_id == 'pm':
            path, expected = Path(p['pmPath']), None
        else:
            a = next((x for x in p['artifacts'] if x['id'] == artifact_id), None)
            if not a:
                raise ProjectError('Unknown artifact')
            path, expected = Path(a['path']), a['sha256']
        with path.open('rb') as source:
            raw = source.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise ProjectError('File too large for preview')
        changed = bool(expected and hashlib.sha256(raw).hexdigest() != expected)
        return dict(path=str(path), changed=changed, text=raw[:64000].decode('utf-8', errors='replace'), truncated=len(raw) > 64000)


def identity_from_env():
    try:
        generation = int(os.environ.get('HERDR_SESSION_GENERATION', '0'))
    except ValueError:
        generation = -1
    return dict(project=os.environ.get('HERDR_PROJECT_ID'), role=os.environ.get('HERDR_PROJECT_ROLE'),
                main=os.environ.get('HERDR_MAIN_ID'), generation=generation,
                run=os.environ.get('HERDR_RUN_ID'), token=os.environ.get('HERDR_PROJECT_TOKEN'))
