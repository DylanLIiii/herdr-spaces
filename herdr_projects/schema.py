"""Additive, transactional ledger migrations. Never infer business completion."""
import json

SCHEMA_VERSION = 2
CAPABILITIES = ['leader-bind', 'guarded-introduction', 'core-command-discovery',
                'pm-configuration', 'coordination-inbox', 'structured-reports',
                'guided-setup', 'role-teams', 'isolated-workspaces', 'artifact-bundles', 'research-contracts']


def project_defaults(project):
    """Defaults for new and migrated projects; preserve every existing field."""
    project.setdefault('setup', dict(state='pending', answers={}, draft=None,
                                    consentAt=None, confirmedRevision=None, checks=[],
                                    nextAction='由指定 PM 询问是否开始配置', skillVersion=None))
    project.setdefault('configuration', dict(revision=0, template=None, roles={},
                                            routing='direct', artifactRoot=None,
                                            followup=dict(enabled=False), history=[]))
    project.setdefault('stage', '')
    project.setdefault('summary', '')
    for item in project.get('items', []):
        item.setdefault('phase', '')
        item.setdefault('waitingOn', None)
        item.setdefault('question', None)
        item.setdefault('checkpointAt', None)
        item.setdefault('lastProgressAt', None)
        item.setdefault('inputArtifactRefs', [])
    for artifact in project.get('artifacts', []):
        artifact.setdefault('kind', 'document')
        artifact.setdefault('storage', 'external')
        artifact.setdefault('disposition', 'undecided')
        artifact.setdefault('validity', 'current')
    return project


def migrate(db):
    # Lock before reading the version: two new clients may open the same ledger.
    db.execute('BEGIN IMMEDIATE')
    try:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1, SCHEMA_VERSION):
            from .store import ProjectError
            raise ProjectError(f'Unsupported ledger schema {version}; do not downgrade this installation')
        for sql in (
            'CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, body TEXT NOT NULL)',
            '''CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, project_id TEXT NOT NULL,
               request_id TEXT NOT NULL, digest TEXT NOT NULL, actor TEXT NOT NULL,
               revision INTEGER NOT NULL, at TEXT NOT NULL, payload TEXT NOT NULL,
               UNIQUE(project_id, request_id))''',
            '''CREATE TABLE IF NOT EXISTS bindings(scope TEXT NOT NULL, terminal TEXT NOT NULL,
               project_id TEXT NOT NULL, role TEXT NOT NULL, run_id TEXT,
               PRIMARY KEY(scope, terminal))''',
            '''CREATE TABLE IF NOT EXISTS inbox(
               seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
               project_id TEXT NOT NULL REFERENCES projects(id), work_item_id TEXT, run_id TEXT,
               kind TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
               notify INTEGER NOT NULL DEFAULT 1, generation INTEGER,
               created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
               receipt TEXT, handled_note TEXT,
               UNIQUE(project_id, id))''',
            'CREATE INDEX IF NOT EXISTS inbox_pending ON inbox(project_id,state,seq)',
            '''CREATE TABLE IF NOT EXISTS service_state(
               name TEXT PRIMARY KEY, body TEXT NOT NULL)''',
        ):
            db.execute(sql)
        if version < SCHEMA_VERSION:
            for row in db.execute('SELECT id,body FROM projects').fetchall():
                p = project_defaults(json.loads(row['body']))
                db.execute('UPDATE projects SET body=? WHERE id=?', (json.dumps(p, ensure_ascii=False), row['id']))
            db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        db.execute('COMMIT')
    except BaseException:
        db.execute('ROLLBACK')
        raise
