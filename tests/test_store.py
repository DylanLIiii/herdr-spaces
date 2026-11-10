import json
from pathlib import Path
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from herdr_projects.store import ProjectError, Store
from herdr_projects.runtime import context, start, reconcile, lock


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.scope_patch = patch('herdr_projects.runtime.connected_scopes', return_value=['core:test', 'default'])
        self.scope_patch.start()
        self.addCleanup(self.scope_patch.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.store = Store(self.home)
        self.store.create('one', 'One', 'A durable goal', self.home)
        self.store.create('two', 'Two', 'Another goal', self.home)
        with self.store.transaction():
            p = self.store.get('one')
            p['main'].update(state='running', generation=1, token='owner-token', scope='default', terminal='t1')
            self.store.bind('one', 't1', 'default', 'main')
            self.store.save(p)
        self.identity = dict(project='one', main=p['main']['id'], generation=1, role='main', token='owner-token')
        self.counter = 0
        self.worker_token = 'test-only-' + uuid.uuid4().hex

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def apply(self, op, **fields):
        self.counter += 1
        return self.store.apply('one', self.store.get('one')['revision'],
                                dict(requestId='r-' + str(self.counter), op=op, **fields), self.identity)

    def task(self, item='work'):
        self.apply('todo.add', id=item, title='Do work', sourceRef='User request')
        self.apply('todo.promote', id=item, brief='Specific scope', acceptanceCriteria=['Verify output'])

    def run_fixture(self):
        self.task()
        with self.store.transaction():
            p = self.store.get('one')
            p['runs'].append(dict(id='run-1', token=self.worker_token, state='running', workItemId='work', terminal='t2', scope='default', reports=[]))
            p['items'][0].update(activeRunId='run-1', status='running')
            self.store.bind('one', 't2', 'default', 'worker', 'run-1')
            self.store.save(p)
        return dict(role='worker', project='one', run='run-1', token=self.worker_token)

    def test_durable_identity_and_todo_promotion(self):
        main = self.store.get('one')['main']['id']
        self.task()
        self.store.close(); self.store = Store(self.home)
        p = self.store.get('one')
        self.assertEqual(main, p['main']['id'])
        self.assertEqual(('work', 'task', 'User request', 'ready'), tuple(p['items'][0][k] for k in ('id', 'kind', 'sourceRef', 'status')))

    def test_wrong_project_worker_and_stale_generation_rejected(self):
        request = dict(requestId='r', op='todo.add', title='X', sourceRef='user')
        for identity in [self.identity | {'project': 'two'}, self.identity | {'role': 'worker'}, self.identity | {'generation': 0}, None]:
            with self.assertRaises(ProjectError):
                self.store.apply('one', 0, request, identity)
        self.assertEqual([], self.store.get('one')['items'])

    def test_optimistic_conflict_and_idempotency(self):
        r = dict(requestId='repeat', op='todo.add', title='X', sourceRef='user')
        self.store.apply('one', 0, r, self.identity)
        self.assertTrue(self.store.apply('one', 0, r, self.identity)['replayed'])
        with self.assertRaises(ProjectError):
            self.store.apply('one', 0, r | {'title': 'Changed'}, self.identity)
        with self.assertRaises(ProjectError):
            self.store.apply('one', 0, r | {'requestId': 'new'}, self.identity)
        self.assertEqual(1, len(self.store.get('one')['items']))

    def test_concurrent_writers_do_not_overwrite(self):
        def mutate(n):
            s = Store(self.home)
            try:
                s.apply('one', 0, dict(requestId=f'parallel-{n}', op='todo.add', title=str(n), sourceRef='user'), self.identity)
                return True
            except ProjectError:
                return False
            finally:
                s.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual([False, True], sorted(pool.map(mutate, (1, 2))))

    def test_report_is_deduplicated_and_never_accepts(self):
        identity = self.run_fixture()
        file = self.home / 'report.md'; file.write_text('Tests passed with explicit evidence')
        request = dict(requestId='report-1', text='Evidence submitted', submitted=True,
                       artifacts=[dict(id='ev1', path=str(file), version='1')])
        self.store.report('one', request, identity)
        self.assertTrue(self.store.report('one', request, identity)['replayed'])
        self.assertEqual('review', self.store.get('one')['items'][0]['status'])
        with self.assertRaises(ProjectError):
            self.store.report('two', request, identity)
        self.apply('artifact.review', id='ev1', status='accepted', note='Read report and verified outputs')
        self.apply('item.status', id='work', status='accepted', note='Meets criterion', evidenceRefs=['ev1'])
        self.assertEqual('accepted', self.store.get('one')['items'][0]['status'])
        with self.assertRaises(ProjectError):
            self.store.report('one', request | {'requestId': 'late'}, identity)

    def test_changed_evidence_requires_new_version(self):
        identity = self.run_fixture()
        file = self.home / 'report.md'; file.write_text('Original evidence')
        self.store.report('one', dict(requestId='report-1', text='submitted', submitted=True, artifacts=[dict(id='ev1', path=str(file))]), identity)
        file.write_text('Changed evidence')
        self.assertTrue(self.store.read_artifact('one', 'ev1')['changed'])
        with self.assertRaises(ProjectError):
            self.apply('artifact.review', id='ev1', status='accepted', note='review')
        with self.assertRaises(ProjectError):
            self.apply('item.status', id='work', status='accepted', note='done', evidenceRefs=['ev1'])

    def test_failed_report_rolls_back_all_artifacts(self):
        identity = self.run_fixture()
        file = self.home / 'report.md'; file.write_text('Evidence')
        with self.assertRaises((ProjectError, OSError)):
            self.store.report('one', dict(requestId='invalid', text='report', artifacts=[dict(id='first', path=str(file)), dict(id='second', path='/missing/report.md')]), identity)
        self.assertEqual([], self.store.get('one')['artifacts'])

    def test_checklist_is_not_task_acceptance_and_cycles_rejected(self):
        self.task('a'); self.task('b')
        self.apply('item.update', id='a', checklist=[dict(title='Step', done=True)], dependencyIds=['b'])
        self.assertEqual('ready', self.store.get('one')['items'][0]['status'])
        with self.assertRaises(ProjectError):
            self.apply('item.update', id='b', dependencyIds=['a'])

    def test_terminal_bindings_and_secrets_are_scoped(self):
        self.assertIsNone(self.store.snapshot('t1', 'other-core')['project'])
        self.assertEqual('one', self.store.snapshot('t1', 'default')['project']['id'])
        self.assertNotIn('owner-token', json.dumps(self.store.snapshot('t1', 'default')))
        with self.assertRaises(ProjectError):
            self.store.bind('two', 't1', 'default', 'main')

    def test_duplicate_legacy_and_canonical_binding_is_not_guessed(self):
        self.store.bind('two', 't1', 'core:test', 'main')
        with self.assertRaisesRegex(ProjectError, 'Ambiguous'):
            self.store.snapshot('t1', scopes=['core:test', 'default'])
        self.assertEqual('two', self.store.snapshot('t1', scopes=['core:test'])['project']['id'])

    @patch('herdr_projects.runtime.hc')
    def test_second_main_does_not_launch(self, hc):
        result = start(self.store, 'one', ['pi', '{context}'])
        self.assertFalse(result['started']); hc.assert_not_called()

    @patch('herdr_projects.runtime.hc', side_effect=ProjectError('timeout'))
    def test_interrupted_launch_preserves_reservation(self, hc):
        with self.assertRaises(ProjectError):
            start(self.store, 'two', ['pi', '{context}'])
        p = self.store.get('two')
        self.assertEqual('starting', p['main']['state'])
        self.assertFalse(start(self.store, 'two', ['pi', '{context}'])['started'])
        self.assertEqual(1, hc.call_count)

    @patch('herdr_projects.runtime.hc')
    def test_reconcile_live_shell_refuses_and_finished_allows_new_generation(self, hc):
        with patch.dict('os.environ', {}, clear=True):
            hc.return_value = {'terminals': [{'address': 't1', 'state': 'live'}]}
            with self.assertRaises(ProjectError):
                reconcile(self.store, 'one')
            hc.return_value = {'terminals': []}
            old_id = self.store.get('one')['main']['id']
            reconcile(self.store, 'one')
            hc.return_value = {'address': 't3'}
            start(self.store, 'one', ['pi', '{context}'])
            p = self.store.get('one')
            self.assertEqual(old_id, p['main']['id'])
            self.assertEqual(2, p['main']['generation'])
            with self.assertRaises(ProjectError):
                self.apply('todo.add', title='stale', sourceRef='stale session')

    def test_process_lock_blocks_recovery(self):
        with lock(self.store, 'one-main-process'):
            with self.assertRaises(ProjectError):
                with lock(self.store, 'one-main-process'):
                    pass

    def test_context_contains_record_interface_and_no_private_token(self):
        output = context(self.store, 'one')
        for value in ('Main / SuperAgent', 'apply', 'revision', '后端 Hooks 未安装'):
            self.assertIn(value, output)
        self.assertNotIn('owner-token', output)

    def test_startup_context_is_bounded_for_large_history(self):
        identity = self.run_fixture()
        with self.store.transaction():
            p = self.store.get('one')
            p['goal'] = '目标' * 5000
            p['items'][0]['brief'] = '范围' * 5000
            p['items'][0]['acceptanceCriteria'] = ['标准' * 5000] * 200
            p['items'] += [dict(id=f'long-{i}', title='标题' * 150, status='open', revision=1, activeRunId=None) for i in range(1000)]
            self.store.save(p)
        self.assertLess(len(context(self.store, 'one', identity['run']).encode()), 110000)
        self.assertIn('1001', context(self.store, 'one'))
        self.assertEqual(1001, len(self.store.get('one')['items']))

    def test_existing_narrative_is_not_overwritten(self):
        pm = self.home / 'external-pm.md'; pm.write_text('Existing decisions')
        self.store.create('linked', 'Linked', 'Goal', self.home, str(pm))
        self.assertEqual('Existing decisions', pm.read_text())


if __name__ == '__main__':
    unittest.main()
