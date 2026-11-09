"""Deterministic test process. This is not an LLM or a substitute agent UI."""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from herdr_projects.store import Store, identity_from_env
from herdr_projects.runtime import start

store = Store()
identity = identity_from_env()
project_id = identity['project']
fixture = Path(store.home) / 'fixture'
fixture.mkdir(exist_ok=True)
assert '最新项目记录' in sys.argv[-1]
assert '后端 Hooks 未安装' in sys.argv[-1]
print('Herdr Projects integration fixture (synthetic data, no model)', flush=True)
print('\033]7501;state=idle:app=projects-fixture\033\\', end='', flush=True)
if identity['role'] == 'worker':
    report = fixture / 'evidence.md'
    report.write_text('# 验证报告\n\n这是隔离环境中的合成测试证据。\n')
    store.report(project_id, dict(requestId='worker-report', text='Deterministic worker submitted evidence', submitted=True,
                                 artifacts=[dict(id='evidence', path=str(report), title='验证报告', version='1')]), identity)
    (fixture / 'worker-done').write_text('ok')
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline and not (fixture / 'release-worker').exists():
        time.sleep(0.1)
else:
    def apply(op, **fields):
        return store.apply(project_id, store.get(project_id)['revision'], dict(requestId='fixture-' + str(store.get(project_id)['revision']), op=op, **fields), identity)
    p = store.get(project_id)
    if not p['items']:
        apply('todo.add', id='future', title='整理可选 Hook 的接入范围', sourceRef='隔离测试场景', brief='基础侧栏无需配置后端 Hook。', nextAction='侧栏验证后细化')
        apply('todo.add', id='work', title='核对账本与执行回报', sourceRef='隔离测试场景', brief='核对任务、Run 与证据关联。')
        apply('todo.promote', id='work', brief='完成结构化报告并由 Main 核验。', acceptanceCriteria=['报告归属正确', '证据内容未发生变化'])
        apply('item.update', id='work', checklist=[dict(title='提交 Worker 报告', done=False), dict(title='核验产物', done=False)])
        worker = start(store, project_id, [sys.executable, str(Path(__file__).resolve()), '{context}'],
                       item_id='work', revision=store.get(project_id)['revision'], identity=identity)
        assert worker['started']
    (fixture / 'main-ready').write_text(json.dumps({'mainId': identity['main'], 'generation': identity['generation'],
                                                 'terminal': os.environ.get('HC_TERMINAL_ID'), 'scope': store.get(project_id)['main']['scope']}))
    # Hold the native terminal for UI navigation tests, without touching other sessions.
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline and not (fixture / 'release').exists():
        time.sleep(0.1)
    if (fixture / 'worker-done').exists() and store.get(project_id)['items'][1]['status'] == 'review':
        assert store.get(project_id)['items'][1]['status'] != 'accepted'
        apply('artifact.review', id='evidence', status='accepted', note='Fixture verified immutable report')
        apply('item.status', id='work', status='accepted', note='Both criteria verified', evidenceRefs=['evidence'])
    (fixture / 'main-done').write_text('ok')
store.close()
