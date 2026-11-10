import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from herdr_projects import cli, runtime
from herdr_projects.store import Store, ProjectError


class ProtocolTests(unittest.TestCase):
    def test_core_identity_is_independent_of_client_alias_and_socket_spelling(self):
        with patch.object(runtime, 'hc', return_value={'core': {'id': 'durable-id'}}):
            with patch.dict(os.environ, {'HC_SOCKET': '/one.sock', 'HC_SESSION': 'one'}, clear=True):
                first = runtime.connected_scopes()
            with patch.dict(os.environ, {'HC_SOCKET': '/alias.sock', 'HC_SESSION': 'two'}, clear=True):
                second = runtime.connected_scopes()
        self.assertEqual('core:durable-id', first[0])
        self.assertEqual(first[0], second[0])
        self.assertNotEqual(first[1:], second[1:])
        self.assertEqual(['core:durable-id', '/one.sock'], first)
        self.assertNotIn('default', second)

    def test_unavailable_core_is_not_replaced_by_a_default_scope(self):
        with patch.object(runtime, 'hc', side_effect=ProjectError('offline')):
            with self.assertRaisesRegex(ProjectError, 'offline'):
                runtime.connected_scopes()

    def test_guarded_artifact_read_refuses_changed_core_or_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp).resolve() / 'ledger'
            store = Store(home)
            store.create('one', 'One', 'Goal', temp)
            store.close()
            command = ['--home', str(home), 'read', '--project', 'one', '--artifact', 'pm',
                       '--core-scope', 'core:expected', '--ledger-home', str(home)]
            with patch.object(runtime, 'connected_scopes', return_value=['core:wrong']), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(1, cli.main(command))
            with patch.object(runtime, 'connected_scopes', return_value=['core:expected']), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(1, cli.main(command[:-1] + [str(home / 'different')]))
            output = io.StringIO()
            with patch.object(runtime, 'connected_scopes', return_value=['core:expected']), contextlib.redirect_stdout(output):
                self.assertEqual(0, cli.main(command))
            result = json.loads(output.getvalue())
            self.assertEqual('core:expected', result['coreScope'])
            self.assertIn('Goal', result['text'])


if __name__ == '__main__':
    unittest.main()
