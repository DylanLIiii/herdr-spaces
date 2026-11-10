import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from herdr_projects import cli, manager, runtime
from herdr_projects.store import Store, ProjectError


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'ledger')
        self.addCleanup(self.store.close)
        self.store.create('p', 'Project', 'Goal', self.root)
        self.skill = self.root / 'custom skill'
        self.skill.mkdir()
        (self.skill / 'SKILL.md').write_text('# Entire PM skill\nRead references/details.md\n')
        (self.skill / 'references').mkdir()
        self.full = '完整规则\n' * 30000 + 'END OF RESOURCE\n'
        (self.skill / 'references/details.md').write_text(self.full)

    def configure_skill(self):
        with self.store.transaction():
            p = self.store.get('p')
            p.update(manager.configure(p, pm_skill=str(self.skill)))
            self.store.save(p)
        return self.store.get('p')

    def invoke(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(['--home', str(self.store.home), *args, '--project', 'p'])
        self.assertEqual(0, code)
        return output.getvalue()

    def test_cli_reads_entire_custom_skill_and_large_reference_without_truncation(self):
        self.configure_skill()
        self.assertEqual((self.skill/'SKILL.md').read_text(), self.invoke('skill'))
        self.assertEqual(self.full, self.invoke('skill', '--resource', 'references/details.md'))
        self.assertEqual(['SKILL.md', 'references/details.md'], json.loads(self.invoke('skill', '--list'))['resources'])

    def test_skill_resources_cannot_escape_configured_directory(self):
        p = self.configure_skill()
        (self.root/'outside.md').write_text('outside')
        (self.skill/'outside-link.md').symlink_to(self.root/'outside.md')
        for resource in ('../outside.md', str(self.root/'outside.md'), 'outside-link.md'):
            with self.assertRaises(ProjectError): manager.read_skill(p, resource)
        self.assertNotIn('outside-link.md', manager.list_resources(p))

    def test_legacy_projects_get_complete_bundled_skill_and_defaults(self):
        self.assertEqual(manager.BUILTIN_SKILL.read_text(), self.invoke('skill'))
        self.assertIn('references/subagents.md', json.loads(self.invoke('skill', '--list'))['resources'])
        self.assertIn('SubAgent', self.invoke('skill', '--resource', 'references/subagents.md'))
        self.assertEqual({'backend':'pi', 'model':None}, json.loads(self.invoke('show'))['subAgent'])

    def test_worker_cli_applies_saved_model_and_tool_but_start_keeps_own_defaults(self):
        with self.store.transaction():
            p = self.store.get('p'); p.update(manager.configure(p, backend='codex', model='saved-model')); self.store.save(p)
        with patch.object(runtime.shutil, 'which', return_value='/bin/agent'), patch.object(cli, 'identity_from_env', return_value={}), patch.object(runtime, 'start', return_value={}) as start:
            self.invoke('worker', '--item', 'task', '--revision', '1')
            self.assertEqual(['codex', '--no-daemon', '--model', 'saved-model', '{context}'], start.call_args.args[2])
            self.invoke('worker', '--item', 'task', '--revision', '1', '--model', 'override')
            self.assertEqual(['codex', '--no-daemon', '--model', 'override', '{context}'], start.call_args.args[2])
            self.invoke('worker', '--item', 'task', '--revision', '1', '--backend', 'claude')
            self.assertEqual(['claude', '{context}'], start.call_args.args[2])
            self.invoke('start')
            self.assertEqual(['pi', '{context}'], start.call_args.args[2])

    def test_custom_argv_is_not_modified_and_missing_program_is_rejected(self):
        p = {'subAgent':{'backend':'pi', 'model':'saved'}}
        custom = ['custom-agent', '--resume', '{context}']
        with patch.object(runtime.shutil, 'which', return_value='/bin/agent'):
            self.assertEqual(custom, manager.worker_command(p, custom=custom))
            with self.assertRaises(ProjectError): manager.worker_command(p, model='ambiguous', custom=custom)
        with patch.object(runtime.shutil, 'which', return_value=None):
            with self.assertRaises(ProjectError): manager.worker_command(p)


if __name__ == '__main__':
    unittest.main()
