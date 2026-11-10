#!/usr/bin/env python3
"""Real isolated Herdr/core verification, using deterministic processes, never LLMs."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.install import install
from scripts.x11_fixture import PrivateDisplay


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', required=True)
    parser.add_argument('--output', default=str(ROOT / 'docs/native'))
    args = parser.parse_args()
    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='hp-native-'))
    env = dict(os.environ)
    for k in list(env):
        if k.startswith('HC_') or k.startswith('HERDR_PROJECT'):
            env.pop(k)
    env.update(HERDR_APP_HOME=str(scratch / 'app'), HC_SESSION='projects-native-test', HC_SOCKET=str(scratch / 'core.sock'),
               XDG_CONFIG_HOME=str(scratch / 'config'), XDG_DATA_HOME=str(scratch / 'data'), XDG_STATE_HOME=str(scratch / 'state'),
               XDG_CACHE_HOME=str(scratch / 'cache'), XDG_RUNTIME_DIR=str(scratch / 'runtime'), LIBGL_ALWAYS_SOFTWARE='1')
    Path(env['XDG_RUNTIME_DIR']).mkdir(mode=0o700)
    ledger = scratch / 'ledger'
    app = str(Path(args.app).resolve())
    window = display = pointer = None
    checks = []
    def call(argv, timeout=20, ok=True):
        r = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=timeout)
        if ok and r.returncode:
            raise RuntimeError(f'{argv[0:3]} failed: {r.stderr or r.stdout}')
        return r
    def jcall(argv, **kwargs):
        return json.loads(call(argv, **kwargs).stdout)
    def wait_for(test, label, seconds=30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            result = test()
            if result:
                return result
            time.sleep(0.15)
        raise RuntimeError('Timed out: ' + label)
    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label); print('PASS ' + label, flush=True)
    project_cli = [sys.executable, str(ROOT / 'project.py'), '--home', str(ledger)]
    try:
        installed = install(env['HERDR_APP_HOME'], scratch / 'bin', ledger,
                            registry_dir=Path(env['XDG_CONFIG_HOME']) / 'herdr-spaces/runtimes')
        # First-run onboarding is unrelated to the plugin. Mark only this
        # temporary app home as skipped before opening its first window.
        (Path(env['HERDR_APP_HOME']) / 'shared.json').write_text(json.dumps({'frame.welcomed': 'skipped'}))
        (Path(env['HERDR_APP_HOME']) / 'settings.json').write_text(json.dumps({'appearance': 'dark'}))
        call(['hc', 'server', 'start'])
        call(project_cli + ['create', 'native-test', '--name', 'Herdr Projects · 验证示例', '--goal', '核对侧栏、任务记录和原生终端导航。', '--cwd', str(ROOT)])
        argv = json.dumps([sys.executable, str(ROOT / 'tests/fixture_agent.py'), '{context}'])
        launch = jcall(project_cli + ['start', '--project', 'native-test', '--command-json', argv])
        address = launch['terminal']
        wait_for(lambda: (ledger / 'fixture/worker-done').exists(), 'worker report')
        wait_for(lambda: (ledger / 'fixture/main-ready').exists(), 'Main registration')
        check('Worker submitted a real report through its assigned run', (ledger / 'fixture/main-ready').exists())
        p = jcall(project_cli + ['show', '--project', 'native-test'])
        check('Idle Worker leaves the task awaiting review', p['items'][1]['status'] == 'review')
        check('Native program reports its own runtime state', jcall(['hc', 'get', address]).get('status', {}).get('state') == 'idle')
        worker = p['runs'][0]
        check('Second start reuses the registered Main', not jcall(project_cli + ['start', '--project', 'native-test', '--command-json', argv])['started'])
        check('Main/Worker terminal bindings route to one project', jcall(project_cli + ['snapshot', '--terminal', address])['project']['id'] == 'native-test')
        recover = call(project_cli + ['reconcile', '--project', 'native-test'], ok=False)
        check('A live Main cannot be recovered into a second owner', recover.returncode != 0)
        display_log = (scratch / 'display.log').open('w')
        display = subprocess.Popen(['Xvfb', '-displayfd', '1', '-screen', '0', '1600x1000x24', '-nolisten', 'tcp'], stdout=subprocess.PIPE, stderr=display_log, text=True)
        display_id = display.stdout.readline().strip()
        if not display_id.isdigit():
            raise RuntimeError('Xvfb did not start: ' + str(scratch / 'display.log'))
        env['DISPLAY'] = ':' + display_id
        window_log = (scratch / 'window.log').open('w')
        window = subprocess.Popen([app], env=env, stdout=window_log, stderr=window_log)
        wait_for(lambda: call([app, 'status'], ok=False).returncode == 0, 'native window')
        # Allow the app's asynchronous machine layout to adopt labeled terminals.
        wait_for(lambda: address in call([app, 'ls'], ok=False).stdout, 'Main terminal adoption')
        os.environ['DISPLAY'] = env['DISPLAY']
        pointer = PrivateDisplay(env['DISPLAY'])
        pointer.resize(1600, 1000)
        call([app, 'do', 'app.theme', json.dumps({'name': 'graphite'})])
        call([app, 'do', 'layout.switch', json.dumps({'name': 'projects'})])
        call([app, 'do', 'tab.rename', json.dumps({'id': p['main']['tab'], 'name': 'Main · 测试程序'})])
        call([app, 'do', 'tab.rename', json.dumps({'id': worker['tab'], 'name': 'Worker · 测试程序'})])
        call([app, 'do', 'pane.focus', json.dumps({'terminal': address})])
        call([app, 'do', 'layout.select', json.dumps({'stack': 'panel-body', 'child': 'project'})])
        call([app, 'do', 'layout.show', json.dumps({'id': 'panel'})])
        # Wait for external exec/read completion before inspecting the actual frame.
        time.sleep(2)
        # Dismiss a possible first-install update toast on this private display.
        pointer.click(1565, 965)
        status = jcall([app, 'status'])
        (output / 'status.json').write_text(json.dumps(status, indent=2, ensure_ascii=False))
        check('Native Project layout renders without host errors or overlays', not status.get('errors') and not status.get('overlays'))
        for page in ('tasks', 'sessions', 'files'):
            call([app, 'do', 'project.' + page])
            time.sleep(0.35)
            call([app, 'shot', str(output / (page + '.png'))])
            check('Native ' + page + ' view has no host errors', not jcall([app, 'status']).get('errors'))
        call([app, 'do', 'project.focus'])
        pointer.key('1'); pointer.key('Down'); pointer.key('Down'); pointer.key('Return')
        call([app, 'shot', str(output / 'task-detail.png')])
        pointer.scroll(1450, 700)
        call([app, 'shot', str(output / 'task-detail-scrolled.png')])
        pointer.key('Escape'); pointer.key('3'); pointer.key('Down'); pointer.key('Down'); pointer.key('Return')
        time.sleep(.5)
        call([app, 'shot', str(output / 'artifact.png')])
        pointer.key('Escape'); pointer.key('2'); pointer.key('Down'); pointer.key('Down'); pointer.key('Return')
        wait_for(lambda: jcall([app, 'status']).get('tab') == worker['tab'], 'keyboard worker navigation')
        check('Keyboard session navigation focuses the existing Worker', True)
        call([app, 'do', 'project.focus'])
        pointer.key('2'); pointer.key('Down'); pointer.key('Return')
        wait_for(lambda: jcall([app, 'status']).get('tab') == p['main']['tab'], 'keyboard Main navigation')
        check('Worker navigation returns to its own Main', True)
        call([app, 'do', 'project.tasks'])
        (Path(env['HERDR_APP_HOME']) / 'settings.json').write_text(json.dumps({'appearance': 'light'}))
        call([app, 'do', 'app.theme', json.dumps({'name': 'paper'})])
        time.sleep(1)
        call([app, 'shot', str(output / 'tasks-light.png')])
        pointer.resize(1024, 800)
        call([app, 'shot', str(output / 'narrow.png')])
        call([app, 'do', 'project.focus'])
        pointer.key('1'); pointer.key('Down'); pointer.key('Down'); pointer.key('Return')
        pointer.scroll(850, 600)
        call([app, 'shot', str(output / 'narrow-detail-scrolled.png')])
        pointer.key('Escape')
        check('Native keyboard/detail/narrow states have no host errors', not jcall([app,'status']).get('errors'))
        pointer.resize(1600, 1000)
        (Path(env['HERDR_APP_HOME']) / 'settings.json').write_text(json.dumps({'appearance': 'dark'}))
        call([app, 'do', 'app.theme', json.dumps({'name': 'graphite'})])
        time.sleep(1)
        call([app, 'do', 'layout.hide', json.dumps({'id': 'panel'})])
        time.sleep(0.25)
        call([app, 'shot', str(output / 'terminal-only.png')])
        check('Closing the panel preserves the live Main', jcall(['hc', 'get', address])['state'] == 'live')
        (ledger / 'fixture/release-worker').write_text('finish')
        wait_for(lambda: jcall(project_cli + ['show','--project','native-test'])['runs'][0]['state'] == 'exited', 'Worker exit')
        check('Worker exit still does not accept the task', jcall(project_cli + ['show','--project','native-test'])['items'][1]['status'] == 'review')
        (ledger / 'fixture/release').write_text('finish')
        wait_for(lambda: (ledger / 'fixture/main-done').exists(), 'Main acceptance')
        wait_for(lambda: jcall(project_cli + ['show', '--project', 'native-test'])['main']['state'] == 'exited', 'Main process exit')
        p = jcall(project_cli + ['show', '--project', 'native-test'])
        check('Only Main acceptance completes the task', p['items'][1]['status'] == 'accepted')
        old_id = p['main']['id']; old_generation = p['main']['generation']
        wait_for(lambda: jcall(['hc','get',address]).get('state') == 'finished', 'Core observing Main exit')
        call(project_cli + ['reconcile', '--project', 'native-test'])
        restarted = jcall(project_cli + ['start', '--project', 'native-test', '--command-json', argv])
        p = restarted['project']
        check('Restart keeps Main identity and advances generation', p['main']['id'] == old_id and p['main']['generation'] == old_generation + 1)
        # Source and installed native checks, independent of mock hosts.
        for target in (ROOT / 'mods/project', ROOT / 'mods/projects-tabs', Path(installed['panel']), Path(installed['tabs'])):
            call([app, 'check', str(target)])
        check('All source and installed mods pass native check', True)
        (output / 'result.json').write_text(json.dumps(dict(passed=len(checks), checks=checks, app=call([app,'--version']).stdout.strip(),
                                                           core=call(['hc','--version']).stdout.strip(), synthetic=True), ensure_ascii=False, indent=2))
    finally:
        # Only this script's isolated window, core and display are touched.
        if pointer:
            pointer.close()
        if window:
            window.terminate()
            try: window.wait(timeout=10)
            except subprocess.TimeoutExpired: window.kill(); window.wait(timeout=5)
        call(['hc', 'server', 'stop'], ok=False)
        if display:
            display.terminate()
            try: display.wait(timeout=5)
            except subprocess.TimeoutExpired: display.kill(); display.wait(timeout=5)
        for file in ('window.log', 'display.log'):
            if (scratch / file).exists():
                shutil.copy2(scratch / file, output / file)
        print('Isolated verification files: ' + str(scratch), flush=True)


if __name__ == '__main__':
    main()
