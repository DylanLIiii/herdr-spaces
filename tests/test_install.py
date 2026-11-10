import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.install import install


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='projects install ')
        self.root = Path(self.tmp.name).resolve()
        self.home, self.bin, self.data = [self.root / s for s in ('app', 'bin', 'data')]
        self.registry = self.root / 'config/herdr-spaces/runtimes'
        self.home.mkdir()
        (self.home / 'settings.json').write_text('{"zoom":1.1}')
        (self.home / 'keys.json').write_text('existing keybindings')

    def install(self, name='projects', **options):
        return install(self.home, self.bin, self.data, name, registry_dir=self.registry, **options)

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_preserves_settings_and_spaces_in_paths(self):
        installed = self.install()
        self.assertEqual('{"zoom":1.1}', (self.home / 'settings.json').read_text())
        self.assertEqual('existing keybindings', (self.home / 'keys.json').read_text())
        r = subprocess.run([installed['binary'], 'list'], capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual([], json.loads(r.stdout))
        layout = json.loads(Path(installed['layout']).read_text())
        self.assertIn('projects-tabs', json.dumps(layout))
        self.assertNotIn('globalThis', Path(installed['panel'], 'main.js').read_text())
        for key in ('panel', 'tabs', 'agents', 'setup'):
            self.assertEqual('none', json.loads(Path(installed[key], 'mod.json').read_text())['place'])
        config = Path(installed['setup'], 'main.js').read_text()
        self.assertIn("from './transport.js'", config)
        self.assertEqual(Path(installed['panel'], 'transport.js').read_text(), Path(installed['setup'], 'transport.js').read_text())

    def test_refuses_overwrite_without_partial_install(self):
        installed = self.install()
        before = {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        with self.assertRaises(FileExistsError):
            self.install()
        after = {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(Path(installed['binary']).exists())

    def test_custom_name_rewrites_only_personal_mod_references(self):
        installed = self.install('trial')
        js = Path(installed['tabs'], 'main.js').read_text()
        self.assertIn('mods/trial-panel/project.svg', js)
        self.assertIn('mods/trial-tabs/win-min.svg', js)
        self.assertIn('mods/files/file.svg', js)
        self.assertNotIn('mods/projects-tabs/', js)

    def test_new_desktop_layout_keeps_the_existing_remote_registration_name(self):
        installed = self.install('spaces-v031', remote_name='spaces-v03')
        layout = json.loads(Path(installed['layout']).read_text())
        configs = []
        def walk(node):
            content = node.get('content', {})
            if content.get('mod') in ('spaces-v031-panel', 'spaces-v031-agents'):
                configs.append(content['props'])
            for child in node.get('children', []):
                walk(child)
        walk(layout)
        self.assertEqual(2, len(configs))
        self.assertTrue(all(config['remoteName'] == 'spaces-v03' for config in configs))
        self.assertTrue((self.registry / 'spaces-v031.json').exists())
        self.assertFalse((self.registry / 'spaces-v03.json').exists())

    def test_runtime_only_registers_target_paths_without_creating_ui_or_ledger(self):
        installed = self.install(runtime_only=True)
        self.assertFalse((self.home / 'mods').exists())
        self.assertFalse((self.home / 'layouts').exists())
        self.assertFalse(self.data.exists())
        discovery = json.loads(Path(installed['discovery']).read_text())
        result = subprocess.run(discovery['command'] + ['probe'], capture_output=True, text=True, check=True)
        probe = json.loads(result.stdout)
        self.assertEqual(1, probe['protocolVersion'])
        self.assertEqual(str(self.data), probe['ledgerHome'])
        self.assertFalse(self.data.exists())
        self.assertEqual('{"zoom":1.1}', (self.home / 'settings.json').read_text())

    def test_discovery_collision_does_not_create_runtime(self):
        self.registry.mkdir(parents=True)
        (self.registry / 'projects.json').write_text('existing')
        with self.assertRaises(FileExistsError):
            self.install(runtime_only=True)
        self.assertFalse((self.home / 'projects-runtime').exists())
        self.assertEqual('existing', (self.registry / 'projects.json').read_text())


if __name__ == '__main__':
    unittest.main()
