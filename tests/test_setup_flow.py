import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from herdr_projects import cli, setup_flow, teams, manager, onboarding, runtime
from herdr_projects.store import ProjectError, Store


class SetupFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'ledger')
        self.addCleanup(self.store.close)
        p = self.store.create('project', 'Project', 'Build a research workflow', self.root)
        self.identity = dict(project='project', role='main', main=p['main']['id'], generation=1, token='test-main')
        with self.store.transaction():
            p = self.store.get('project')
            p['main'].update(state='running', generation=1, token='test-main', scope='core:test', terminal='t1')
            self.store.save(p)
        self.counter = 0

    def apply(self, op, **fields):
        self.counter += 1
        return self.store.apply('project', self.store.get('project')['revision'],
                                dict(requestId=f'change-{self.counter}', op=op, **fields), self.identity)

    def configure(self):
        self.apply('setup.begin', sourceRef='User said begin')
        value = teams.template('development')
        self.apply('setup.draft', configuration=value)
        self.apply('setup.confirm', draftRevision=1, sourceRef='User approved the team and storage plan')
        return self.store.get('project')['configuration']

    def test_consent_required_and_defer_resume_preserves_answers(self):
        with self.assertRaises(ProjectError):
            self.apply('setup.draft', configuration=teams.template())
        self.apply('setup.invite')
        invited = self.store.get('project')['setup']['invitedAt']
        self.apply('setup.invite')
        self.assertEqual(invited, self.store.get('project')['setup']['invitedAt'])
        self.apply('setup.defer')
        self.assertEqual('deferred', self.store.get('project')['setup']['state'])
        self.apply('setup.begin', sourceRef='Now start')
        self.apply('setup.answer', key='work', value='Research', nextAction='Choose available tools')
        consent = self.store.get('project')['setup']['consentAt']
        self.apply('setup.defer')
        self.apply('setup.begin', sourceRef='Continue')
        self.assertEqual(consent, self.store.get('project')['setup']['consentAt'])
        self.assertEqual({'work':'Research'}, self.store.get('project')['setup']['answers'])

    def test_draft_conflict_and_configuration_history(self):
        first = self.configure()
        with self.assertRaisesRegex(ProjectError, 'changed'):
            self.apply('setup.confirm', draftRevision=1, sourceRef='Duplicate with new request id')
        self.apply('setup.draft', configuration=teams.template('research'))
        with self.assertRaises(ProjectError):
            self.apply('setup.confirm', draftRevision=1, sourceRef='Stale draft')
        self.apply('setup.confirm', draftRevision=2, sourceRef='Approved revised research team')
        p = self.store.get('project')
        self.assertEqual(2, p['configuration']['revision'])
        self.assertEqual('development', p['configuration']['history'][0]['value']['template'])
        self.assertEqual('research', p['configuration']['history'][1]['value']['template'])
        self.assertEqual(1, first['revision'])
        self.assertEqual(1, p['main']['generation'])
        self.assertEqual([], p['runs'])

    def test_fixture_cannot_claim_real_capability_ready(self):
        config = self.configure()
        for key in setup_flow.required_checks(config):
            self.apply('setup.check', configurationRevision=1, key=key, status='passed', mode='fixture', evidence='Protocol fixture passed')
        with self.assertRaisesRegex(ProjectError, 'not verified'):
            self.apply('setup.finish')
        self.assertEqual('verifying', self.store.get('project')['setup']['state'])
        for key in setup_flow.required_checks(config):
            self.apply('setup.check', configurationRevision=1, key=key, status='passed', mode='observed', evidence='Observed result recorded by the PM')
        self.apply('setup.finish')
        self.assertEqual('ready', self.store.get('project')['setup']['state'])

    def test_check_must_match_current_config(self):
        self.configure()
        for revision, key, status in [(0, 'storage', 'passed'), (1, 'invented', 'passed'), (1, 'storage', 'ready')]:
            with self.assertRaises(ProjectError):
                self.apply('setup.check', configurationRevision=revision, key=key, status=status, evidence='evidence')

    def test_custom_pm_still_gets_complete_setup_skill(self):
        skill = self.root / 'custom.md'; skill.write_text('Custom PM')
        with self.store.transaction():
            p = self.store.get('project'); p['pmSkill'] = str(skill); self.store.save(p)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, cli.main(['--home', str(self.store.home), 'skill', '--project', 'project', '--setup']))
        self.assertEqual(setup_flow.skill(), out.getvalue())
        intro = onboarding.introduction(self.store, 'project')
        self.assertIn('--setup', intro)
        self.assertIn('询问是否现在开始配置', intro)

    @patch.object(runtime, 'connected_scopes', return_value=['core:test'])
    @patch.object(runtime, 'hc', side_effect=lambda args: dict(address=args[1], state='live'))
    def test_configuration_survives_handoff_and_reopen(self, hc, scopes):
        self.configure()
        before = self.store.get('project')['setup']
        onboarding.bind(self.store, 't2', 'core:test', 'project', replace_generation=1)
        other = Store(self.store.home)
        try:
            self.assertEqual(before, other.get('project')['setup'])
            with self.assertRaises(ProjectError):
                self.apply('setup.defer')
        finally:
            other.close()

    def test_templates_and_validation(self):
        for name in teams.TEMPLATES:
            self.assertEqual(name, teams.validate(teams.template(name))['template'])
        invalid = teams.template('research')
        invalid['roles']['research']['backend'] = 'pi'
        with self.assertRaises(ProjectError): teams.validate(invalid)
        invalid = teams.template()
        invalid['roles']['worker']['isolation'] = 'readonly'
        with self.assertRaises(ProjectError): teams.validate(invalid)
        invalid = teams.template(); invalid['token'] = 'forbidden'
        with self.assertRaises(ProjectError): teams.validate(invalid)
        invalid = teams.template(); invalid['artifactRoot'] = 'relative'
        with self.assertRaises(ProjectError): teams.validate(invalid)

    @patch('shutil.which', return_value='/bin/fixture')
    def test_role_routing_and_backend_commands(self, which):
        config = teams.validate(teams.template('mixed', 'coding-hub')) | dict(revision=1)
        project = dict(configuration=config)
        worker = teams.resolve(project)
        self.assertEqual('remote-magpie/group/craft', worker['model'])
        self.assertEqual('worktree', worker['isolation'])
        self.assertEqual(['pi', '--model', worker['model'], '{context}'], manager.worker_command(project, profile=worker))
        research = teams.resolve(project, role='research')
        self.assertIsNone(research['tier'])
        self.assertEqual(['feynman', '--new-session', 'deepresearch', '{context}'], manager.worker_command(project, profile=research))
        direct = teams.resolve(project, backend='opencode', model='provider/model')
        self.assertEqual(['opencode', '--standalone', 'mini', '--model', 'provider/model', '--prompt', '{context}'], manager.worker_command(project, profile=direct))

    def test_fallback_only_before_launch_if_binary_is_missing(self):
        config = teams.validate(teams.template('development', 'coding-hub')) | dict(revision=1)
        with patch('shutil.which', side_effect=lambda name: '/bin/opencode' if name == 'opencode' else None):
            profile = teams.resolve(dict(configuration=config))
        self.assertEqual('opencode', profile['backend'])
        self.assertEqual('magpie/remote-magpie/group/craft', profile['model'])
        self.assertIn('not installed', profile['fallbackReason'])


if __name__ == '__main__':
    unittest.main()
