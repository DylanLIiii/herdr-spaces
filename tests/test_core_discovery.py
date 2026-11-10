import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from herdr_projects.runtime import core_command
from herdr_projects.store import ProjectError

ROOT = Path(__file__).resolve().parent.parent


class CoreDiscoveryTests(unittest.TestCase):
    def test_setup_finds_installed_core_outside_background_path(self):
        """A machine exec can omit ~/.local/bin while the interactive shell has it."""
        with tempfile.TemporaryDirectory(prefix='spaces core path ') as directory:
            home = Path(directory)
            core = home / '.local/bin/hc'
            core.parent.mkdir(parents=True)
            core.write_text('#!' + sys.executable + '\nimport json,sys\n'
                'if sys.argv[1]=="--version": print("hc 0.1.19"); sys.exit(0)\n'
                'value={"core":{"id":"fixture-core"}} if sys.argv[1]=="server" else '
                '{"address":"t31","state":"live","cwd":' + repr(str(home)) + ',"status":{"state":"idle","app":"fixture"}}\n'
                'print(json.dumps(value))\n')
            core.chmod(0o755)
            env = {k:v for k,v in os.environ.items() if not k.startswith(('HC_', 'HERDR_PROJECT'))}
            env.update(HOME=str(home), PATH=str(home / 'empty-path'), HC_SOCKET=str(home / 'fixture.sock'))
            result = subprocess.run([sys.executable, str(ROOT / 'project.py'), '--home', str(home / 'ledger'),
                'setup', '--terminal', 't31'], env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(0, result.returncode, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual('t31', data['terminal'])
            self.assertEqual('core:fixture-core', data['coreScope'])
            self.assertEqual(str(home), data['cwd'])

    def executable(self, path, version='hc 0.1.19'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!' + sys.executable + '\nprint(' + repr(version) + ')\n')
        path.chmod(0o755)
        return path

    def test_official_install_works_without_the_optional_hc_alias(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'HOME':temp, 'PATH':temp+'/empty'}, clear=True):
            target = self.executable(Path(temp) / '.local/bin/herdr-core')
            self.assertEqual(str(target), core_command())

    def test_custom_install_directory_and_explicit_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='custom core ') as temp:
            target = self.executable(Path(temp) / 'custom bin/herdr-core')
            with patch.dict(os.environ, {'HOME':temp, 'PATH':temp+'/empty', 'HC_INSTALL_DIR':str(target.parent)}, clear=True):
                self.assertEqual(str(target), core_command())
            with patch.dict(os.environ, {'HOME':temp, 'PATH':temp+'/empty', 'HERDR_PROJECTS_HC':str(target)}, clear=True):
                self.assertEqual(str(target), core_command())

    def test_unrelated_hc_on_path_is_not_used_as_herdr(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'HOME':temp, 'PATH':temp+'/bin'}, clear=True):
            self.executable(Path(temp) / 'bin/hc', 'another program 1.0')
            expected = self.executable(Path(temp) / '.local/bin/herdr-core')
            self.assertEqual(str(expected), core_command())

    def test_invalid_override_never_falls_back_to_another_core_binary(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'HOME':temp, 'PATH':temp+'/bin', 'HERDR_PROJECTS_HC':temp+'/missing'}, clear=True):
            self.executable(Path(temp) / 'bin/herdr-core')
            with self.assertRaisesRegex(ProjectError, 'HERDR_PROJECTS_HC'):
                core_command()

    def test_absent_binary_reports_resolution_failure_not_uncertain_launch(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'HOME':temp, 'PATH':temp+'/empty'}, clear=True):
            with self.assertRaisesRegex(ProjectError, '未找到可用的 Herdr Core'):
                core_command()


if __name__ == '__main__':
    unittest.main()
