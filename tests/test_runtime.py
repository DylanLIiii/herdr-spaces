import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from herdr_projects.store import Store

ROOT = Path(__file__).resolve().parent.parent


class NativeProcessTests(unittest.TestCase):
    def test_ctrl_c_remains_owned_by_native_program(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            child = home / 'native_program.py'
            child.write_text('''import signal,sys,time\nfrom pathlib import Path\np=Path(sys.argv[1])\nsignal.signal(signal.SIGINT,lambda *_:(p/'interrupted').write_text('handled'))\n(p/'ready').write_text('ready')\nwhile not (p/'release').exists():time.sleep(.02)\n''')
            store = Store(home)
            store.create('one', 'Native test', 'Preserve input semantics', home)
            with store.transaction():
                p = store.get('one')
                p['main'].update(state='starting', generation=1, token='test-token', scope='test',
                                 command=[sys.executable, str(child), str(home), '{context}'])
                store.save(p)
            env = dict(os.environ, HC_TERMINAL_ID='test-terminal')
            proc = subprocess.Popen([sys.executable, str(ROOT / 'project.py'), '--home', str(home), '_run',
                                     '--project', 'one', '--token', 'test-token'], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                deadline = time.monotonic() + 5
                while not (home / 'ready').exists() and time.monotonic() < deadline and proc.poll() is None:
                    time.sleep(.02)
                self.assertTrue((home / 'ready').exists(), 'Native child did not start')
                os.killpg(proc.pid, signal.SIGINT)
                deadline = time.monotonic() + 2
                while not (home / 'interrupted').exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue((home / 'interrupted').exists(), 'Native child did not receive Ctrl+C')
                time.sleep(.35)
                self.assertIsNone(proc.poll(), 'Wrapper killed the native program after Ctrl+C')
                (home / 'release').write_text('done')
                _, stderr = proc.communicate(timeout=5)
                self.assertEqual(0, proc.returncode, stderr.decode())
                self.assertEqual('exited', store.get('one')['main']['state'])
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.communicate(timeout=5)
                store.close()
