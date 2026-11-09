import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.install import install


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='projects install ')
        self.root = Path(self.tmp.name)
        self.home, self.bin, self.data = [self.root / s for s in ('app', 'bin', 'data')]
        self.home.mkdir()
        (self.home / 'settings.json').write_text('{"zoom":1.1}')
        (self.home / 'keys.json').write_text('existing keybindings')

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_preserves_settings_and_spaces_in_paths(self):
        installed = install(self.home, self.bin, self.data)
        self.assertEqual('{"zoom":1.1}', (self.home / 'settings.json').read_text())
        self.assertEqual('existing keybindings', (self.home / 'keys.json').read_text())
        r = subprocess.run([installed['binary'], 'list'], capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual([], json.loads(r.stdout))
        layout = json.loads(Path(installed['layout']).read_text())
        self.assertIn('projects-tabs', json.dumps(layout))
        self.assertNotIn('globalThis', Path(installed['panel'], 'main.js').read_text())

    def test_refuses_overwrite_without_partial_install(self):
        installed = install(self.home, self.bin, self.data)
        before = {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        with self.assertRaises(FileExistsError):
            install(self.home, self.bin, self.data)
        after = {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(Path(installed['binary']).exists())

    def test_custom_name_rewrites_only_personal_mod_references(self):
        installed = install(self.home, self.bin, self.data, 'trial')
        js = Path(installed['tabs'], 'main.js').read_text()
        self.assertIn('mods/trial-panel/project.svg', js)
        self.assertIn('mods/trial-tabs/win-min.svg', js)
        self.assertIn('mods/files/file.svg', js)
        self.assertNotIn('mods/projects-tabs/', js)


if __name__ == '__main__':
    unittest.main()
