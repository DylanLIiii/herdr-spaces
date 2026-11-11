"""Contracts at the real launch boundary, not just bookkeeping fixtures."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from herdr_projects import runtime, teams
from herdr_projects.store import Store


class NativeAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'ledger'); self.addCleanup(self.store.close)
        p = self.store.create('one', 'Project', 'Native child', self.temp.name)
        self.identity = dict(role='main', project='one', main=p['main']['id'], generation=1, token='test')
        with self.store.transaction():
            p = self.store.get('one')
            p['main'].update(state='running', token='test', generation=1, terminal='t1', scope='core:test', space='space', tab='pm-tab')
            self.store.save(p)
        for n, (op, fields) in enumerate([
            ('todo.add', dict(title='Native child', sourceRef='user')),
            ('todo.promote', dict(brief='Read code', acceptanceCriteria=['Native status']))]):
            self.store.apply('one', n, dict(op=op, id='task', requestId='req-'+str(n), **fields), self.identity)

    def test_worker_is_core_child_without_forced_new_tab(self):
        profile = teams.template('mixed')['roles']['explore'] | dict(role='explore')
        with patch.object(runtime, 'connected_scopes', return_value=['core:test']), patch.object(runtime, 'hc', return_value=dict(address='t2')) as hc:
            runtime.start(self.store, 'one', ['fixture', '{context}'], item_id='task', revision=2, identity=self.identity, profile=profile)
        args = hc.call_args.args[0]
        self.assertIn('--parent', args)
        self.assertEqual('t1', args[args.index('--parent')+1])
        self.assertNotIn('--no-parent', args)
        self.assertIn('--outlive-parent', args)
        self.assertFalse(any(x.startswith('herdr.tab=') for x in args))
        self.assertFalse(any(x.startswith('herdr.space=') for x in args))
        run = self.store.get('one')['runs'][0]
        self.assertEqual('t1', run['parentTerminal'])
        self.assertEqual('pm-tab', run['tab'])

    def test_opencode_status_is_run_scoped_and_preserves_existing_config(self):
        from herdr_projects.native_agents import environment
        run = dict(id='run-test', execution=dict(backend='opencode'), command=['opencode','--standalone','mini','--prompt','{context}'])
        old = dict(PATH='/bin', OPENCODE_CONFIG_CONTENT=json.dumps(dict(plugins=['existing'], model='original/model')))
        env, argv = environment(run, old, run['command'], tty='/dev/ttys123')
        config = json.loads(env['OPENCODE_CONFIG_CONTENT'])
        self.assertEqual('existing', config['plugins'][0])
        self.assertEqual('original/model', config['model'])
        self.assertEqual('/dev/ttys123', env['HERDR_SPACES_STATUS_TTY'])
        self.assertEqual(env['HERDR_SPACES_SESSION_ID'], argv[argv.index('--session')+1])
        self.assertNotIn('HERDR_SPACES_SESSION_ID', old)


if __name__ == '__main__': unittest.main()
