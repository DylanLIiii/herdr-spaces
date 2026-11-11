"""PM-led configuration state; binding is independent of setup consent."""
import copy
import hashlib
from pathlib import Path

from .store import ProjectError, now, text
from . import teams

SETUP_SKILL = Path(__file__).resolve().parent / 'skills/herdr-spaces-setup/SKILL.md'
OPERATIONS = ('setup.invite', 'setup.begin', 'setup.defer', 'setup.answer', 'setup.draft',
              'setup.confirm', 'setup.check', 'setup.finish')


def skill():
    return SETUP_SKILL.read_text(encoding='utf-8')


def skill_version():
    return hashlib.sha256(skill().encode()).hexdigest()


def required_checks(config):
    backends = {profile['backend'] for role, profile in config['roles'].items() if role != 'pm' and profile['enabled']}
    result = ['storage', 'reporting']
    if config.get('followup', {}).get('enabled'):
        result.append('coordination')
    for backend in sorted(backends):
        result += [f'backend.{backend}.{level}' for level in ('installed', 'authentication', 'model')]
        if backend == 'feynman':
            result.append('backend.feynman.search')
    return result


def operation(project, request):
    setup, config = project['setup'], project['configuration']
    op = request['op']
    if op == 'setup.invite':
        # Retrying the invitation after resume never creates another question.
        setup['skillVersion'] = skill_version()
        if not setup.get('invitedAt'):
            setup['invitedAt'] = now()
        setup['nextAction'] = '等待用户决定是否开始配置' if not setup.get('consentAt') else setup['nextAction']
    elif op == 'setup.defer':
        setup['resumeState'] = setup['state'] if setup['state'] != 'deferred' else setup.get('resumeState', 'pending')
        setup.update(state='deferred', nextAction='用户选择稍后继续', deferredAt=now())
    elif op == 'setup.begin':
        source = text(request.get('sourceRef'), 'user consent source')
        if setup['state'] != 'ready':
            setup['state'] = setup.get('resumeState', 'configuring') if setup.get('consentAt') else 'configuring'
            if setup['state'] in ('pending', 'deferred'):
                setup['state'] = 'configuring'
            setup.setdefault('consentSource', source)
            setup['consentAt'] = setup.get('consentAt') or now()
            setup['nextAction'] = request.get('nextAction') or ('检查配置能力' if setup['state'] == 'verifying' else '检查环境并补齐缺失信息')
    else:
        if not setup.get('consentAt') or setup['state'] in ('pending', 'deferred'):
            raise ProjectError('Ask whether to begin setup and record explicit consent first')
        if op == 'setup.answer':
            if setup['state'] != 'configuring':
                raise ProjectError('Answers belong to a configuration draft; start an explicit revision first')
            key = text(request.get('key'), 'answer key', 100)
            value = request.get('value')
            if not isinstance(value, (str, bool, int)) or (isinstance(value, str) and len(value) > 4000):
                raise ProjectError('An answer must be short text, a boolean or a number')
            setup['answers'][key] = value
            setup['nextAction'] = text(request.get('nextAction'), 'nextAction', 2000)
        elif op == 'setup.draft':
            proposed = teams.validate(request.get('configuration'))
            setup['draft'] = proposed
            setup['draftRevision'] = setup.get('draftRevision', 0) + 1
            setup['draftBaseRevision'] = config['revision']
            setup.update(state='configuring', nextAction='向用户展示具体方案和差异，等待确认')
        elif op == 'setup.confirm':
            if not setup.get('draft') or request.get('draftRevision') != setup.get('draftRevision'):
                raise ProjectError('Configuration draft changed; read and confirm the current draft')
            if setup.get('draftBaseRevision') != config['revision']:
                raise ProjectError('Configuration changed; prepare a new draft')
            source = text(request.get('sourceRef'), 'configuration confirmation source')
            # Store only portable settings in history, not another nested history.
            values = teams.validate(setup['draft'])
            history = copy.deepcopy(config.get('history', []))
            history.append(dict(revision=config['revision'] + 1, at=now(), sourceRef=source,
                                mainId=project['main']['id'], generation=project['main']['generation'],
                                skillVersion=setup.get('skillVersion'), value=copy.deepcopy(values)))
            project['configuration'] = dict(values, revision=config['revision'] + 1, history=history)
            setup.update(state='verifying', confirmedRevision=config['revision'] + 1,
                         checks=[], nextAction='检查回报、存储与已启用后端的实际能力')
        elif op == 'setup.check':
            if setup['state'] != 'verifying' or request.get('configurationRevision') != config['revision']:
                raise ProjectError('Check results must refer to the current confirmed configuration')
            key, status = request.get('key'), request.get('status')
            if key not in required_checks(config) or status not in ('passed', 'failed', 'unverified'):
                raise ProjectError('Unknown capability check or status')
            mode = request.get('mode', 'observed')
            if mode not in ('observed', 'fixture'):
                raise ProjectError('Check mode must be observed or fixture')
            check = dict(key=key, status=status, mode=mode, evidence=text(request.get('evidence'), 'check evidence'),
                         configurationRevision=config['revision'], at=now())
            setup['checks'] = [entry for entry in setup['checks'] if entry['key'] != key] + [check]
        elif op == 'setup.finish':
            if setup['state'] != 'verifying':
                raise ProjectError('Confirm the configuration and verify it first')
            checks = {entry['key']: entry for entry in setup['checks']}
            missing = [key for key in required_checks(config) if key not in checks or checks[key]['status'] != 'passed' or checks[key]['mode'] != 'observed']
            if missing:
                raise ProjectError('Configuration saved but capabilities are not verified: ' + ', '.join(missing))
            setup.update(state='ready', nextAction='配置已就绪；由用户指定下一项工作', completedAt=now())
        else:
            raise ProjectError('Unknown setup operation')
    setup['updatedAt'] = now()
