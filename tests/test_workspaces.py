from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from herdr_projects import runtime, teams, workspaces
from herdr_projects.store import Store, ProjectError


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'; self.repo.mkdir()
        self.git('init', '-q')
        (self.repo / 'source.txt').write_text('base')
        self.git('add', 'source.txt')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture base')
        self.store = Store(self.root / 'ledger')
        self.addCleanup(self.store.close)
        p = self.store.create('p', 'Project', 'Goal', self.repo)
        self.identity = dict(project='p', main=p['main']['id'], generation=1, role='main', token='test')
        with self.store.transaction():
            p = self.store.get('p')
            p['main'].update(state='running', generation=1, token='test', scope='core:test', terminal='t1')
            p['configuration'] = teams.validate(teams.template('mixed')) | dict(revision=1, history=[])
            self.store.save(p)
        self.counter = 0
        self.addCleanup(patch.stopall)
        patch.object(runtime, 'connected_scopes', return_value=['core:test']).start()
        patch('shutil.which', return_value='/bin/fixture').start()
        self.hc = patch.object(runtime, 'hc', side_effect=lambda args: dict(address='t-' + str(self.counter))).start()

    def git(self, *args):
        result = subprocess.run(['git', '-C', str(self.repo), *args], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout.strip()

    def task(self, task_id):
        for op, fields in [('todo.add', dict(title=task_id, sourceRef='test')),
                           ('todo.promote', dict(brief='Isolated change', acceptanceCriteria=['Verify isolation']))]:
            self.counter += 1
            self.store.apply('p', self.store.get('p')['revision'], dict(requestId=f'r-{self.counter}', op=op, id=task_id, **fields), self.identity)

    def launch(self, task_id, role='worker', override=None):
        self.task(task_id)
        profile = teams.resolve(self.store.get('p'), role=role)
        if override: profile.update(override)
        return runtime.start(self.store, 'p', ['fixture', '{context}'], item_id=task_id,
                             revision=self.store.get('p')['revision'], identity=self.identity, profile=profile)

    def test_parallel_writers_have_independent_worktrees_and_snapshots(self):
        self.launch('first')
        self.launch('second')
        runs = self.store.get('p')['runs']
        self.assertNotEqual(runs[0]['cwd'], runs[1]['cwd'])
        self.assertNotEqual(runs[0]['branch'], runs[1]['branch'])
        (Path(runs[0]['cwd']) / 'source.txt').write_text('first writer')
        self.assertEqual('base', (Path(runs[1]['cwd']) / 'source.txt').read_text())
        self.assertEqual('base', (self.repo / 'source.txt').read_text())
        self.assertEqual(1, runs[0]['execution']['configurationRevision'])
        self.assertEqual(self.git('rev-parse', 'HEAD'), runs[0]['baseCommit'])
        self.assertIn('pm', runs[0]['skillSnapshot'])
        self.assertTrue(all('--cwd' in call.args[0] for call in self.hc.call_args_list))

    def test_unisolated_worker_rejected_even_with_no_other_writer(self):
        with self.assertRaisesRegex(ProjectError, 'isolated worktree'):
            self.launch('first', override=dict(isolation='project'))
        self.assertEqual([], self.store.get('p')['runs'])
        self.hc.assert_not_called()

    def test_old_preferences_resolve_to_isolation_without_mutating_saved_config(self):
        legacy = {'subAgent': {'backend': 'pi', 'model': None}}
        self.assertEqual('worktree', teams.resolve(legacy)['isolation'])
        p = self.store.get('p')
        p['configuration']['roles']['worker']['isolation'] = 'project'
        self.assertEqual('worktree', teams.resolve(p)['isolation'])
        self.assertEqual('project', p['configuration']['roles']['worker']['isolation'])
        with self.assertRaises(ProjectError):
            teams.validate({k:p['configuration'][k] for k in ('template','routing','roles','followup','artifactRoot')})

    def test_research_has_separate_durable_directory(self):
        self.launch('research', role='research')
        run = self.store.get('p')['runs'][0]
        self.assertEqual(run['cwd'], run['outputRoot'])
        self.assertNotEqual(str(self.repo), run['cwd'])
        self.assertTrue(Path(run['cwd']).is_dir())
        self.assertIn('provenance', runtime.context(self.store, 'p', run['id']))

    def test_autoresearch_requires_bounded_confirmed_contract(self):
        with self.assertRaisesRegex(ProjectError, 'benchmark contract'):
            self.launch('research', role='research', override=dict(workflow='autoresearch'))
        self.assertEqual([], self.store.get('p')['runs'])
        contract = dict(objective='Improve accuracy', metric='accuracy', unit='percent', direction='maximize',
                        benchmark=['python3', 'benchmark.py'], allowedPaths=['experiment.py'],
                        environment='fixture environment', maxIterations=2, userConfirmation='User approved two iterations')
        workspaces.research_contract(dict(researchContract=contract), dict(role='research', workflow='autoresearch'))
        contract['maxIterations'] = 0
        with self.assertRaises(ProjectError):
            workspaces.research_contract(dict(researchContract=contract), dict(role='research', workflow='autoresearch'))

    def test_failed_preparation_retains_evidence_and_does_not_launch(self):
        with patch.object(workspaces, 'prepare', side_effect=ProjectError('No disk space')):
            with self.assertRaisesRegex(ProjectError, 'preparation failed'):
                self.launch('failed')
        self.hc.assert_not_called()
        p = self.store.get('p')
        self.assertEqual('exited', p['runs'][0]['state'])
        self.assertEqual('blocked', p['items'][0]['status'])
        self.assertEqual('No disk space', p['runs'][0]['error'])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM collaboration WHERE kind='failed'").fetchone()[0])

    def test_changed_input_version_cannot_be_consumed_by_a_new_run(self):
        self.task('source-task')
        evidence = self.root / 'evidence.md'; evidence.write_text('Original findings')
        self.store.apply('p', self.store.get('p')['revision'], dict(requestId='evidence-register', op='artifact.add',
            id='evidence', workItemId='source-task', sourceRef='fixture', path=str(evidence)), self.identity)
        self.task('consumer')
        self.store.apply('p', self.store.get('p')['revision'], dict(requestId='input-link', op='item.update',
            id='consumer', inputArtifactRefs=['evidence']), self.identity)
        evidence.write_text('Unreviewed replacement')
        with self.assertRaisesRegex(ProjectError, 'changed'):
            runtime.start(self.store, 'p', ['fixture', '{context}'], item_id='consumer',
                          revision=self.store.get('p')['revision'], identity=self.identity,
                          profile=teams.resolve(self.store.get('p')))
        self.hc.assert_not_called()
        self.assertEqual('blocked', self.store.item(self.store.get('p'), 'consumer')['status'])

    def test_unknown_launch_keeps_workspace_for_reconciliation(self):
        self.hc.side_effect = ProjectError('Unknown delivery')
        with self.assertRaises(ProjectError): self.launch('uncertain')
        p = self.store.get('p')
        self.assertEqual('starting', p['runs'][0]['state'])
        self.assertTrue(Path(p['runs'][0]['cwd']).is_dir())
        with self.assertRaises(ProjectError):
            runtime.start(self.store, 'p', ['fixture', '{context}'], item_id='uncertain',
                          revision=p['revision'], identity=self.identity, profile=teams.resolve(p))
        self.assertEqual(1, self.hc.call_count)


if __name__ == '__main__':
    unittest.main()
