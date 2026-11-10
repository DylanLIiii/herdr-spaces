import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from herdr_projects import onboarding, runtime, manager
from herdr_projects.store import Store, ProjectError, identity_from_env
from scripts.install import runtime_bundle
from scripts.bootstrap import prepare


class LeaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.store = Store(self.home / 'ledger')
        self.addCleanup(self.store.close)
        self.term = dict(address='t1', state='live', cwd=str(self.home), labels={'herdr.space':'existing-space'}, status=dict(state='idle', app='fixture'))
        self.calls = []
        def hc(argv):
            self.calls.append(argv)
            if argv[0] == 'get': return self.term | {'address': argv[1]}
            return {'ok': True}
        for name, options in [('hc', dict(side_effect=hc)), ('connected_scopes', dict(return_value=['core:test']))]:
            mock = patch.object(runtime, name, **options); mock.start(); self.addCleanup(mock.stop)

    def bind(self, project='p', terminal='t1'):
        return onboarding.bind(self.store, terminal, 'core:test', project, 'Project', 'A goal', str(self.home))

    def test_existing_terminal_becomes_one_durable_leader_without_starting_a_process(self):
        result = self.bind(); p = result['project']
        again = self.bind()['project']
        self.assertEqual(p['main']['id'], again['main']['id'])
        self.assertEqual(1, again['main']['generation'])
        self.assertEqual('attached', p['main']['mode'])
        self.assertEqual('existing-space', p['main']['space'])
        self.assertEqual('p', self.store.snapshot('t1', scopes=['core:test'])['project']['id'])
        self.assertFalse(any(cmd[0] in ('run', 'send') for cmd in self.calls))
        self.assertNotIn('token', p['main'])

    def test_second_leader_and_cross_project_rebinding_are_rejected(self):
        self.bind()
        with self.assertRaises(ProjectError): self.bind(terminal='t2')
        with self.assertRaises(ProjectError): self.bind(project='other')
        with self.assertRaises(ProjectError): onboarding.bind(self.store,'t1','core:wrong','p')
        self.assertEqual(['p'], [p['id'] for p in self.store.snapshot()['projects']])

    def test_explicit_rebind_preserves_records_revokes_old_identity_and_rotates_generation(self):
        original = self.bind()['project']
        with patch.dict(os.environ, {'HC_TERMINAL_ID':'t1'}, clear=True):
            old_identity = identity_from_env(self.store)
            self.store.apply('p', 1, dict(requestId='task', op='todo.add', title='Keep me', sourceRef='user'), old_identity)
        onboarding.notify(self.store, 'p', 'core:test', 1)
        result = onboarding.bind(self.store, 't2', 'core:test', 'p', replace_generation=1)['project']
        self.assertEqual(original['main']['id'], result['main']['id'])
        self.assertEqual(2, result['main']['generation'])
        self.assertEqual('Keep me', result['items'][0]['title'])
        self.assertIsNone(result['main']['notice'])
        self.assertIsNone(self.store.snapshot('t1', scopes=['core:test'])['binding'])
        with self.assertRaises(ProjectError): self.store.check_main(self.store.get('p'), old_identity)
        with patch.dict(os.environ, {'HC_TERMINAL_ID':'t1'}, clear=True):
            self.assertIsNone(identity_from_env(self.store)['project'])
        with patch.dict(os.environ, {'HC_TERMINAL_ID':'t2'}, clear=True):
            self.store.check_main(self.store.get('p'), identity_from_env(self.store))
        with self.assertRaises(ProjectError): onboarding.notify(self.store, 'p', 'core:test', 1)
        self.assertEqual('sent', onboarding.notify(self.store, 'p', 'core:test', 2)['state'])
        self.assertEqual('main.rebind', self.store.history('p')[0]['payload']['op'])
        self.assertIn(['label', 't1', 'projects.role=former-main'], self.calls)
        self.assertFalse(any(c[0] in ('run', 'kill', 'close') for c in self.calls))

    def test_old_managed_process_exit_cannot_overwrite_rebound_pm(self):
        self.store.create('p', 'Project', 'Goal', self.home)
        with self.store.transaction():
            p = self.store.get('p')
            p['main'].update(state='starting', mode='managed', generation=1, token='old-token',
                             scope='core:test', command=['fixture', '{context}'])
            self.store.save(p)
        def native_process(*args, **kwargs):
            onboarding.bind(self.store, 't2', 'core:test', 'p', replace_generation=1)
            return type('Exit', (), {'returncode':0})()
        with patch.dict(os.environ, {'HC_TERMINAL_ID':'t1'}, clear=True), patch.object(runtime.subprocess, 'run', side_effect=native_process):
            self.assertEqual(0, runtime.execute(self.store, 'p', 'old-token'))
        p = self.store.get('p')
        self.assertEqual(('running', 'attached', 't2', 2), tuple(p['main'][key] for key in ('state', 'mode', 'terminal', 'generation')))
        self.assertNotIn('exitCode', p['main'])

    def test_rebind_rejects_stale_generation_wrong_core_and_busy_introduction(self):
        self.bind()
        for options in ({'replace_generation':0}, {'replace_generation':2}):
            with self.assertRaises(ProjectError): onboarding.bind(self.store, 't2', 'core:test', 'p', **options)
        with patch.object(runtime, 'connected_scopes', return_value=['core:other']):
            with self.assertRaises(ProjectError): onboarding.bind(self.store, 't2', 'core:other', 'p', replace_generation=1)
        with runtime.lock(self.store, 'p-intro'):
            with self.assertRaises(ProjectError): onboarding.bind(self.store, 't2', 'core:test', 'p', replace_generation=1)
        self.assertEqual('t1', self.store.get('p')['main']['terminal'])
        self.assertIsNone(self.store.snapshot('t2', scopes=['core:test'])['binding'])

    def test_rebind_rejects_a_terminal_owned_by_another_project(self):
        self.bind()
        self.bind(project='other', terminal='t2')
        with self.assertRaises(ProjectError): onboarding.bind(self.store, 't2', 'core:test', 'p', replace_generation=1)
        self.assertEqual('t1', self.store.get('p')['main']['terminal'])

    def test_exited_attached_terminal_can_be_rebound_explicitly(self):
        self.bind()
        with self.store.transaction():
            p = self.store.get('p'); p['main'].update(state='exited', exitCode=1, endedAt='old'); self.store.save(p)
        result = onboarding.bind(self.store, 't1', 'core:test', 'p', replace_generation=1)['project']
        self.assertEqual(2, result['main']['generation'])
        self.assertNotIn('exitCode', result['main'])
        self.assertNotIn('endedAt', result['main'])

    def test_pm_settings_persist_and_refresh_introduction_without_changing_identity(self):
        self.bind()
        onboarding.notify(self.store, 'p', 'core:test', 1)
        result = onboarding.bind(self.store, 't1', 'core:test', 'p', replace_generation=1,
                                 worker_backend='codex', worker_model='test-model')['project']
        self.assertEqual(1, result['main']['generation'])
        self.assertIsNone(result['main']['notice'])
        self.assertEqual({'backend':'codex', 'model':'test-model'}, result['subAgent'])
        self.assertIn('test-model', runtime.context(self.store, 'p'))
        self.assertIn('skill --project p', onboarding.introduction(self.store, 'p'))
        self.assertIn('完整读取', runtime.context(self.store, 'p'))
        self.assertEqual(result['subAgent'], onboarding.setup(self.store, 't1')['projects'][0]['subAgent'])
        with patch.object(runtime.shutil, 'which', return_value='/bin/codex'):
            self.assertEqual(['codex', '--no-daemon', '--model', 'test-model', '{context}'], manager.worker_command(self.store.get('p')))

    def test_invalid_skill_does_not_create_or_replace_a_project(self):
        with self.assertRaises(OSError):
            onboarding.bind(self.store, 't1', 'core:test', 'new', 'Name', 'Goal', str(self.home), pm_skill=str(self.home/'missing'))
        self.assertEqual([], self.store.snapshot()['projects'])
        self.bind()
        with self.assertRaises(ProjectError):
            onboarding.bind(self.store, 't2', 'core:test', 'p', replace_generation=1, pm_skill='relative/SKILL.md')
        self.assertEqual('t1', self.store.get('p')['main']['terminal'])

    def test_terminal_derived_credentials_work_only_for_explicit_attached_leader(self):
        self.bind()
        with patch.dict(os.environ, {'HC_TERMINAL_ID':'t1'}, clear=True):
            identity = identity_from_env(self.store)
            self.store.apply('p', 1, dict(requestId='add', op='todo.add', title='Task', sourceRef='user'), identity)
        with patch.dict(os.environ, {'HC_TERMINAL_ID':'t2'}, clear=True):
            self.assertIsNone(identity_from_env(self.store)['project'])
        with patch.dict(os.environ, {'HC_TERMINAL_ID':'t1', 'HERDR_PROJECT_TOKEN':'stale'}, clear=True):
            self.assertIsNone(identity_from_env(self.store)['project'])

    def test_introduction_is_idle_guarded_and_deduplicated(self):
        p = self.bind()['project']
        result = onboarding.notify(self.store, 'p', 'core:test', p['main']['generation'])
        self.assertEqual('sent', result['state'])
        onboarding.notify(self.store, 'p', 'core:test', p['main']['generation'])
        sends = [cmd for cmd in self.calls if cmd[0] == 'send']
        self.assertEqual(1, len(sends)); self.assertEqual(['--if','idle','--json'], sends[0][-3:])
        self.assertNotIn('--force', sends[0]); self.assertIn('context --project p', sends[0][2])

    def test_busy_blocked_and_shell_terminals_are_never_typed_into(self):
        self.bind()
        for status in ({'state':'working','app':'pi'}, {'state':'blocked','app':'pi'}, {'state':'idle'}):
            self.term['status'] = status
            self.assertEqual('waiting', onboarding.notify(self.store,'p','core:test',1)['state'])
        self.assertFalse(any(cmd[0] == 'send' for cmd in self.calls))

    def test_uncertain_send_cannot_be_replayed_by_retrying_setup(self):
        self.bind()
        original = runtime.hc.side_effect
        def fail(argv):
            if argv[0]=='send': raise ProjectError('connection lost')
            return original(argv)
        with patch.object(runtime,'hc',side_effect=fail) as call:
            self.assertEqual('uncertain',onboarding.notify(self.store,'p','core:test',1)['state'])
            self.assertEqual('uncertain',onboarding.notify(self.store,'p','core:test',1)['state'])
            self.assertEqual(1,len([c for c in call.call_args_list if c.args[0][0]=='send']))

    def test_attached_recovery_requires_the_actual_terminal_to_exit(self):
        main_id = self.bind()['project']['main']['id']
        with self.assertRaises(ProjectError): runtime.reconcile(self.store,'p')
        self.term['state']='finished'
        runtime.reconcile(self.store,'p')
        self.term['state']='live'
        p=self.bind(terminal='t2')['project']
        self.assertEqual(main_id,p['main']['id']);self.assertEqual(2,p['main']['generation'])


class PreparationTests(unittest.TestCase):
    def test_missing_remote_runtime_is_prepared_idempotently_without_creating_ledger(self):
        with tempfile.TemporaryDirectory(prefix='spaces prepare ') as temp, patch.dict(os.environ, {'XDG_CONFIG_HOME':temp+'/config','XDG_DATA_HOME':temp+'/data'}, clear=True):
            first=prepare('projects',runtime_bundle())
            second=prepare('projects',runtime_bundle())
            self.assertTrue(first['prepared']);self.assertFalse(second['prepared'])
            self.assertEqual(first['command'],second['command'])
            self.assertFalse(Path(first['ledgerHome']).exists())
            self.assertTrue(Path(temp+'/config/herdr-spaces/runtimes/projects.json').is_file())
            installed = Path(first['command'][1]).parent / 'herdr_projects/skills/project-manager'
            self.assertEqual(manager.BUILTIN_SKILL.read_text(), (installed/'SKILL.md').read_text())
            self.assertTrue((installed/'references/subagents.md').is_file())

    def test_preparation_upgrade_preserves_the_existing_custom_ledger(self):
        import sys
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'XDG_CONFIG_HOME':temp+'/config','XDG_DATA_HOME':temp+'/data'}, clear=True):
            registry=Path(temp)/'config/herdr-spaces/runtimes';registry.mkdir(parents=True)
            ledger=Path(temp)/'custom ledger';ledger.mkdir();(ledger/'existing.txt').write_text('keep')
            legacy=[sys.executable,'-c','import json;print(json.dumps('+repr({'protocolVersion':1,'version':'0.3.0','capabilities':['leader-bind','guarded-introduction'],'ledgerHome':str(ledger)})+'))']
            (registry/'projects.json').write_text(json.dumps({'protocolVersion':1,'command':legacy}))
            result=prepare('projects',runtime_bundle())
            self.assertTrue(result['prepared']);self.assertEqual(str(ledger),result['ledgerHome'])
            self.assertEqual('keep',(ledger/'existing.txt').read_text())
            self.assertEqual(result['command'],json.loads((registry/'projects.json').read_text())['command'])

    def test_prepare_rejects_untrusted_paths_or_changed_bundle(self):
        bundle=runtime_bundle();bundle['files']['../escape']='bad'
        with self.assertRaises(ValueError):prepare('projects',bundle)
        bundle=runtime_bundle();bundle['sha256']='wrong'
        with self.assertRaises(ValueError):prepare('projects',bundle)


if __name__ == '__main__':
    unittest.main()
