"""Deterministic native PM / research performer for integration tests; no model."""
import json
import os
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from herdr_projects import coordination, runtime, teams, setup_flow
from herdr_projects.store import Store, identity_from_env, uid

root = Path(sys.argv[1])
store = Store(root / 'ledger')
project_id = 'research-loop'


def status(value='idle'):
    print('\033]7501;state=' + value + ':app=pi\033\\', end='', flush=True)


def apply(op, **fields):
    return store.apply(project_id, store.get(project_id)['revision'], dict(requestId=uid('fixture'), op=op, **fields), identity_from_env(store))


def marker(name, value):
    (root / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False))


def configure():
    assert '是否开始' in setup_flow.skill()
    apply('setup.invite')
    print('要现在开始配置这个项目吗？（确定性 fixture 的模拟用户回答）', flush=True)
    apply('setup.defer')
    apply('setup.begin', sourceRef='Synthetic operator: begin configuration')
    apply('setup.answer', key='workflow', value='mixed', nextAction='Review available team')
    proposed = teams.template('mixed')
    apply('setup.draft', configuration=proposed)
    apply('setup.confirm', draftRevision=1, sourceRef='Synthetic operator approved fixture team')
    config = store.get(project_id)['configuration']
    for key in setup_flow.required_checks(config):
        apply('setup.check', configurationRevision=1, key=key, status='unverified', mode='fixture', evidence='Model/search calls intentionally not performed by this synthetic fixture')
    marker('configured', store.public(store.get(project_id)))


def launch_research():
    apply('todo.add', id='study', title='研究可靠协调与成果保管', sourceRef='Synthetic operator request')
    apply('todo.promote', id='study', brief='Fixture research with traceable files; no claims about actual model quality',
          acceptanceCriteria=['Published brief retains sources and provenance after execution cleanup'])
    profile = teams.resolve(store.get(project_id), 'research')
    profile['customCommand'] = True
    result = runtime.start(store, project_id, [sys.executable, str(Path(__file__).resolve()), str(root), '{context}'],
                           item_id='study', revision=store.get(project_id)['revision'], identity=identity_from_env(store), profile=profile)
    marker('launched', result)


def review():
    events = coordination.inbox(store, project_id)['entries']
    if events:
        apply('inbox.acknowledge', ids=[event['id'] for event in events])
    apply('artifact.review', id='research-brief', status='accepted', note='Fixture: read published files and checked the cited repository evidence')
    apply('artifact.disposition', id='research-brief', disposition='adopted', note='Adopt durable inbox with explicit PM handling; implementation follow-up required')
    apply('item.status', id='study', status='accepted', note='Published fixture brief and provenance verified', evidenceRefs=['research-brief'])
    apply('artifact.followup', id='research-brief', workItemId='validate-inbox', title='验证通知恢复语义', brief='Check interrupted delivery against the adopted study')
    if events:
        apply('inbox.handle', ids=[event['id'] for event in events], note='Reviewed report, recorded decision and created a linked follow-up')
    marker('reviewed', store.public(store.get(project_id)))


def worker():
    identity = identity_from_env(store)
    p = store.get(project_id)
    run = next(run for run in p['runs'] if run['id'] == identity['run'])
    out = Path(run['outputRoot'])
    status('working')
    store.report(project_id, dict(requestId='fixture-progress', text='核对源码与恢复边界', phase='核对来源',
                                 kind='progress', nextAction='形成可追溯简报', checkpointAt='2020-01-01T00:00:00Z'), identity)
    files = []
    for role in ('plan', 'draft', 'cited', 'brief', 'provenance'):
        path = out / (role + '.md')
        path.write_text('# 可靠协调与成果保管\n\n这是确定性测试产物，不是真实模型研究结果。\n\n'
                        '## 结论\n\n将回报持久化，并由 PM 明确记录处理结果。\n\n'
                        '## 依据与适用范围\n\n[来源实现](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/effects.ts)\n\n'
                        '本示例验证项目协议与产物生命周期；未验证模型研究质量。\n')
        files.append(dict(path=path.name, role=role))
    store.report(project_id, dict(requestId='fixture-submitted', text='研究包已提交，等待 PM 核验', kind='submitted', phase='交付核验',
        artifacts=[dict(id='research-brief', workItemId='study', title='可靠协调与成果保管', kind='research', sourceRef='DeepSeek Effects implementation',
            bundle=dict(root=str(out), entrypoint='brief.md', files=files, workflow='deepresearch',
                claims=[dict(id='durable-inbox', text='先保存事件，再交付通知；处理状态独立记录。', verification='verified',
                    note='Fixture source locator; test proves lifecycle, not research quality', limitations=['单项目机器；实际模型未参与'],
                    sources=[dict(reference='https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/effects.ts', locator='Effects.enqueue / attempt', accessedAt='2026-11-11')])]))]), identity)
    marker('worker-submitted', dict(run=run['id'], outputRoot=str(out)))
    print('Research fixture submitted', flush=True)
    status('done')


try:
    if os.environ.get('HERDR_PROJECT_ROLE') == 'worker':
        worker()
    else:
        print('Herdr Spaces PM integration fixture — synthetic, no model', flush=True)
        status()
        for line in sys.stdin:
            value = line.strip()
            if value.startswith('fixture:'):
                action = value.split(':', 1)[1]
                status('working')
                try:
                    {'setup': configure, 'research': launch_research, 'review': review}[action]()
                except Exception:
                    marker('error', dict(action=action, traceback=traceback.format_exc()))
                    traceback.print_exc()
                status()
            elif ' inbox --project ' in line:
                marker('notification', dict(terminal=os.environ.get('HC_TERMINAL_ID'), line=line.strip()))
                print('Inbox notification received; awaiting explicit fixture review.', flush=True)
                status()
finally:
    store.close()
