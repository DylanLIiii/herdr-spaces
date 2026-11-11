import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from herdr_projects import coordination as c, runtime, onboarding
from herdr_projects.store import ProjectError, Store


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'ledger')
        self.addCleanup(self.store.close)
        p = self.store.create('one', 'One', 'Goal', self.root)
        self.main = dict(role='main', project='one', main=p['main']['id'], generation=1, token='main-test')
        with self.store.transaction():
            p = self.store.get('one')
            p['main'].update(state='running', generation=1, terminal='t1', scope='core:test', token='main-test')
            self.store.save(p)
        self.counter = 0
        self.apply('todo.add', id='work', title='Research', sourceRef='user')
        self.apply('todo.promote', id='work', brief='Read sources', acceptanceCriteria=['Trace key claims'])
        with self.store.transaction():
            p = self.store.get('one')
            p['runs'].append(dict(id='run-one', workItemId='work', state='running', token='worker-test', reports=[]))
            p['items'][0].update(status='running', activeRunId='run-one')
            self.store.save(p)
        self.worker = dict(role='worker', project='one', run='run-one', token='worker-test')

    def apply(self, op, **values):
        self.counter += 1
        return self.store.apply('one', self.store.get('one')['revision'],
                                dict(requestId=f'apply-{self.counter}', op=op, **values), self.main)

    def report(self, report_id='report-one', **values):
        return self.store.report('one', dict(requestId=report_id, text='Progress', **values), self.worker)

    def entries(self):
        return c.inbox(self.store, 'one')['entries']

    def terminal(self, args):
        if args[0] == 'get':
            return dict(address=args[1], state='live', status=dict(state='idle', app='pi'))
        return dict(ok=True)

    def test_transactional_migration_preserves_legacy_data_and_rejects_future(self):
        home = self.root / 'old'
        home.mkdir()
        db = sqlite3.connect(home / 'projects.sqlite3')
        db.execute('CREATE TABLE projects(id TEXT PRIMARY KEY,body TEXT NOT NULL)')
        old = self.store.get('one')
        old.pop('configuration'); old.pop('setup')
        db.execute('INSERT INTO projects VALUES(?,?)', ('one', json.dumps(old)))
        db.execute('PRAGMA user_version=1'); db.commit(); db.close()
        with_store = Store(home)
        try:
            p = with_store.get('one')
            self.assertEqual(old['main'], p['main'])
            self.assertEqual(old['items'], p['items'])
            self.assertEqual(old['revision'], p['revision'])
            self.assertEqual('pending', p['setup']['state'])
            self.assertEqual(2, with_store.db.execute('PRAGMA user_version').fetchone()[0])
            with_store.db.execute('PRAGMA user_version=99')
        finally:
            with_store.close()
        with self.assertRaisesRegex(ProjectError, 'Unsupported ledger schema'):
            Store(home)

    def test_duplicate_reports_and_progress_coalescing(self):
        self.report(phase='Reading', checkpointAt='2030-01-01T00:00:00Z')
        self.assertTrue(self.report(phase='Reading', checkpointAt='2030-01-01T00:00:00Z')['replayed'])
        self.report('report-two', phase='Verifying')
        rows = self.entries()
        self.assertEqual(1, len(rows))
        self.assertEqual(0, rows[0]['notify'])
        self.assertEqual('Verifying', rows[0]['body']['phase'])
        self.assertEqual(2, len(self.store.get('one')['runs'][0]['reports']))

    def test_invalid_artifact_rolls_back_report_and_inbox(self):
        with self.assertRaises(OSError):
            self.report(kind='submitted', artifacts=[dict(path=str(self.root / 'missing'), id='evidence')])
        self.assertEqual([], self.entries())
        self.assertEqual([], self.store.get('one')['runs'][0]['reports'])
        self.assertEqual('running', self.store.get('one')['items'][0]['status'])

    def test_structured_question_and_submission(self):
        self.report(kind='question', question=dict(text='Which benchmark?', recipient='user', recommendation='Use baseline'))
        self.assertEqual('user', self.store.get('one')['items'][0]['waitingOn'])
        self.report('finished', kind='submitted')
        item = self.store.get('one')['items'][0]
        self.assertEqual('review', item['status'])
        self.assertEqual('pm', item['waitingOn'])
        self.assertIsNone(item['question'])
        self.assertEqual(2, len(self.entries()))

    def test_question_on_progress_still_notifies_pm(self):
        self.report(kind='progress', question=dict(text='Choose scope', recipient='user'))
        self.assertEqual(1, self.entries()[0]['notify'])
        self.report('routine', phase='Continue independent work')
        self.assertEqual(2, len(self.entries()))
        self.assertEqual('Choose scope', self.entries()[0]['body']['question']['text'])

    def test_invalid_progress_is_rejected_without_mutation(self):
        for values in [dict(kind='question'), dict(waitingOn='anybody'), dict(checkpointAt='tomorrow'),
                       dict(checkpointAt='2030-01-01T00:00:00'), dict(kind='progress', submitted=True),
                       dict(question=dict(text='Q', recipient='user'), waitingOn='pm')]:
            with self.assertRaises(ProjectError):
                self.report(**values)
        self.assertEqual([], self.entries())

    def test_checkpoint_once_across_restart_without_relaunch(self):
        self.report(checkpointAt='2020-01-01T00:00:00Z')
        c.due_checkpoints(self.store, 'one')
        other = Store(self.store.home)
        try:
            c.due_checkpoints(other, 'one')
        finally:
            other.close()
        self.assertEqual(1, len([e for e in self.entries() if e['kind'] == 'checkpoint']))
        self.assertEqual(1, len(self.store.get('one')['runs']))
        self.assertEqual('running', self.store.get('one')['items'][0]['status'])

    def test_acknowledgement_and_handling_are_explicit(self):
        self.report(kind='submitted')
        event = self.entries()[0]['id']
        with self.assertRaises(ProjectError):
            self.apply('inbox.handle', ids=[event], note='Done')
        self.apply('inbox.acknowledge', ids=[event])
        self.assertEqual('acknowledged', self.entries()[0]['state'])
        self.apply('inbox.handle', ids=[event], note='Read sources; requested revision')
        self.assertEqual([], self.entries())
        self.assertEqual('review', self.store.get('one')['items'][0]['status'])
        self.assertEqual('handled', c.inbox(self.store, 'one', include_handled=True)['entries'][0]['state'])

    @patch.object(runtime, 'connected_scopes', return_value=['core:test'])
    def test_send_does_not_acknowledge_and_is_not_repeated(self, scopes):
        self.report(kind='submitted')
        with patch.object(runtime, 'hc', side_effect=self.terminal) as hc:
            self.assertEqual('sent', c.notify_pm(self.store, 'one'))
            self.assertEqual('quiet', c.notify_pm(self.store, 'one'))
            self.assertEqual(1, len([call for call in hc.call_args_list if call.args[0][0] == 'send']))
        self.assertEqual('sent', self.entries()[0]['state'])
        self.assertEqual(1, len(self.entries()[0]['receipt']))

    @patch.object(runtime, 'connected_scopes', return_value=['core:test'])
    def test_busy_pm_defers_and_unknown_send_never_retries(self, scopes):
        self.report(kind='submitted')
        with patch.object(runtime, 'hc', return_value=dict(state='live', status=dict(state='working', app='pi'))) as hc:
            self.assertEqual('waiting', c.notify_pm(self.store, 'one'))
            self.assertEqual(1, hc.call_count)
        def uncertain(args):
            if args[0] == 'send':
                raise ProjectError('Timeout after sending')
            return self.terminal(args)
        with patch.object(runtime, 'hc', side_effect=uncertain):
            self.assertEqual('uncertain', c.notify_pm(self.store, 'one'))
        with patch.object(runtime, 'hc') as hc:
            self.assertEqual('quiet', c.notify_pm(self.store, 'one'))
            hc.assert_not_called()
        self.assertEqual('uncertain', self.entries()[0]['state'])

    def test_crash_reservation_recovers_as_uncertain(self):
        self.report(kind='submitted')
        self.store.db.execute("UPDATE inbox SET state='sending'")
        c.recover_sends(self.store)
        self.assertEqual('uncertain', self.entries()[0]['state'])

    @patch.object(runtime, 'connected_scopes', return_value=['core:test'])
    def test_handoff_keeps_events_and_rejects_old_pm(self, scopes):
        self.report(kind='submitted')
        event = self.entries()[0]['id']
        self.apply('inbox.acknowledge', ids=[event])
        with patch.object(runtime, 'hc', side_effect=self.terminal):
            onboarding.bind(self.store, 't3', 'core:test', 'one', replace_generation=1)
        self.assertEqual('queued', self.entries()[0]['state'])
        with self.assertRaises(ProjectError):
            self.apply('inbox.handle', ids=[event], note='Old PM')
        p = self.store.get('one')
        self.main.update(generation=p['main']['generation'], token=p['main']['token'])
        self.apply('inbox.acknowledge', ids=[event])
        self.apply('inbox.handle', ids=[event], note='New PM verified the report')
        self.assertEqual([], self.entries())

    def test_inbox_pagination_keeps_every_event(self):
        self.report(kind='blocked')
        self.report('second', kind='failed')
        first = c.inbox(self.store, 'one', limit=1)
        second = c.inbox(self.store, 'one', after=first['nextAfter'], limit=1)
        self.assertEqual(2, first['pending'])
        self.assertNotEqual(first['entries'][0]['id'], second['entries'][0]['id'])
        self.assertIsNone(second['nextAfter'])

    def test_disabled_service_does_not_call_core(self):
        with patch.object(runtime, 'hc') as hc:
            self.assertEqual({}, c.service_tick(self.store))
            hc.assert_not_called()


if __name__ == '__main__':
    unittest.main()
