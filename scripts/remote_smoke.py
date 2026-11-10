#!/usr/bin/env python3
"""Real Core machine transport and native UI, isolated loopback hosts, no SSH/LLMs."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.install import install
from scripts.x11_fixture import PrivateDisplay

BRIDGE = '''import json,os,pathlib,signal,subprocess,sys,time
settings=json.loads(pathlib.Path(sys.argv[1]).read_text())
gate=pathlib.Path(sys.argv[2])
if gate.exists(): sys.exit(1)
env={k:v for k,v in os.environ.items() if not k.startswith(('HC_','HERDR_PROJECT'))}
env.update(settings)
child=subprocess.Popen(['/bin/sh','-c',sys.argv[-1]],env=env,start_new_session=True)
try:
 while child.poll() is None:
  if gate.exists():
   os.killpg(child.pid,signal.SIGTERM)
   break
  time.sleep(.1)
 sys.exit(child.wait(timeout=5))
finally:
 if child.poll() is None:
  os.killpg(child.pid,signal.SIGKILL)
  child.wait()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', required=True)
    parser.add_argument('--output', default=str(ROOT / 'docs/remote'))
    args = parser.parse_args()
    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='spaces-remote-'))
    base = {k: v for k, v in os.environ.items() if not k.startswith(('HC_', 'HERDR_PROJECT'))}
    def environment(name):
        extra = dict(HC_SOCKET=str(scratch / (name + '.sock')), HC_SESSION=name,
                     HERDR_APP_HOME=str(scratch / name / 'app'), LIBGL_ALWAYS_SOFTWARE='1')
        for key, part in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache'), ('XDG_RUNTIME_DIR', 'runtime')]:
            extra[key] = str(scratch / name / part); Path(extra[key]).mkdir(parents=True, mode=0o700)
        return base | extra, extra
    client, _ = environment('client')
    second, _ = environment('second')
    server, server_settings = environment('server')
    bridge = scratch / 'bridge.py'; bridge.write_text(BRIDGE)
    settings = scratch / 'server.json'; settings.write_text(json.dumps(server_settings))
    gate = scratch / 'disconnected'
    via = shlex.join([sys.executable, str(bridge), str(settings), str(gate)])
    app = str(Path(args.app).resolve())
    pointer = window = display = None
    checks = []
    def call(argv, env=client, ok=True, timeout=20):
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=timeout)
        if ok and result.returncode:
            raise RuntimeError(f'{argv[:3]}: {result.stderr or result.stdout}')
        return result
    def jcall(argv, **kwargs):
        return json.loads(call(argv, **kwargs).stdout)
    def wait_for(fn, label, seconds=30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            result = fn()
            if result:
                return result
            time.sleep(.15)
        raise RuntimeError('Timed out: ' + label)
    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label); print('PASS ' + label, flush=True)
    def do(command_name, **kw):
        return call([app, 'do', command_name, json.dumps(kw)])
    def remote(command, env=client, machine='fixture', ok=True):
        return call(['hc', 'exec', '--on', machine, '--timeout', '10', '--', *command], env=env, ok=ok)
    def add_machine(env=client, name='fixture'):
        return call(['hc', 'machine', 'add', '--name', name, '--session', 'server', '--via', via], env=env)
    try:
        desktop = install(client['HERDR_APP_HOME'], scratch / 'client/bin', scratch / 'client/ledger', registry_dir=Path(client['XDG_CONFIG_HOME']) / 'herdr-spaces/runtimes')
        target = install(server['HERDR_APP_HOME'], scratch / 'server/bin', scratch / 'server/ledger', runtime_only=True,
                         registry_dir=Path(server['XDG_CONFIG_HOME']) / 'herdr-spaces/runtimes')
        check('Remote installation creates runtime only, without desktop files or a ledger', not Path(server['HERDR_APP_HOME'], 'mods').exists() and not Path(target['dataHome']).exists())
        for env in (client, second, server):
            call(['hc', 'server', 'start'], env=env)
        add_machine(); add_machine(second, 'another-name')
        # Use the actual panel discovery program, not a test-only alternate route.
        discovery = call(['node', '--input-type=module', '-e', "import {discoverRuntime} from './mods/project/transport.js';process.stdout.write(discoverRuntime)"], env=base).stdout
        remote_cli = ['python3', '-c', discovery, 'projects']
        probe = json.loads(remote(remote_cli + ['probe']).stdout)
        check('Core machine exec discovers target paths and compatible protocol', probe['protocolVersion'] == 1 and probe['ledgerHome'] == target['dataHome'])
        local_cli = [desktop['binary']]
        call(local_cli + ['create', 'same-id', '--name', 'Local fixture', '--goal', 'Local records stay local', '--cwd', str(scratch / 'client')])
        local_launch = jcall(local_cli + ['start', '--project', 'same-id', '--command-json', json.dumps([sys.executable, '-c', 'import time; time.sleep(180)', '{context}'])])
        remote(remote_cli + ['create', 'same-id', '--name', 'Remote project · 验证示例', '--goal', '账本、Main、Worker 与证据均在项目机器。', '--cwd', str(scratch / 'server')])
        fixture = Path(target['runtime']) / 'fixture_agent.py'; shutil.copy2(ROOT / 'tests/fixture_agent.py', fixture)
        argv = json.dumps([sys.executable, str(fixture), '{context}'])
        launched = json.loads(remote(remote_cli + ['start', '--project', 'same-id', '--command-json', argv]).stdout)
        address = launched['terminal']; ledger = Path(target['dataHome'])
        wait_for(lambda: (ledger / 'fixture/main-ready').exists() and (ledger / 'fixture/worker-done').exists(), 'remote fixture')
        snapshot = json.loads(remote(remote_cli + ['snapshot', '--terminal', address]).stdout)
        p = snapshot['project']; worker = p['runs'][0]
        check('Main and Worker write only the project machine ledger', p['items'][1]['status'] == 'review' and not jcall(local_cli + ['show', '--project', 'same-id'])['items'])
        check('Same terminal and project ids on separate cores resolve to separate projects', address == local_launch['terminal'] and p['name'].startswith('Remote') and jcall(local_cli + ['snapshot', '--terminal', address])['project']['name'] == 'Local fixture')
        other = json.loads(remote(remote_cli + ['snapshot', '--terminal', address], second, 'another-name').stdout)
        check('Two clients with different machine aliases share one Main and core identity', other['project']['main']['id'] == p['main']['id'] and other['coreScopes'][0] == snapshot['coreScopes'][0])
        check('Second client cannot create a duplicate Main', not json.loads(remote(remote_cli + ['start', '--project', 'same-id', '--command-json', argv], second, 'another-name').stdout)['started'])
        evidence_args = ['read', '--project', 'same-id', '--artifact', 'evidence', '--core-scope', snapshot['coreScopes'][0], '--ledger-home', snapshot['ledgerHome']]
        evidence = json.loads(remote(remote_cli + evidence_args).stdout)
        check('Evidence is read and hashed on the project machine', '合成测试证据' in evidence['text'] and not evidence['changed'])
        check('Neither client stores the remote evidence files', not Path(desktop['dataHome'], 'fixture').exists() and not Path(second['XDG_DATA_HOME'], 'herdr-projects').exists())
        app_home = Path(client['HERDR_APP_HOME'])
        (app_home / 'shared.json').write_text(json.dumps({'frame.welcomed': 'skipped'}))
        (app_home / 'settings.json').write_text(json.dumps({'appearance': 'dark'}))
        display_log = (scratch / 'display.log').open('w')
        display = subprocess.Popen(['Xvfb', '-displayfd', '1', '-screen', '0', '1600x1000x24', '-nolisten', 'tcp'], stdout=subprocess.PIPE, stderr=display_log, text=True)
        display_id = display.stdout.readline().strip()
        if not display_id.isdigit():
            raise RuntimeError('Private display failed')
        client['DISPLAY'] = ':' + display_id
        window_log = (scratch / 'window.log').open('w')
        window = subprocess.Popen([app], env=client, stdout=window_log, stderr=window_log)
        wait_for(lambda: call([app, 'status'], ok=False).returncode == 0, 'window')
        wait_for(lambda: 'fixture/' + address in call([app, 'ls'], ok=False).stdout, 'remote adoption')
        os.environ['DISPLAY'] = client['DISPLAY']; pointer = PrivateDisplay(client['DISPLAY']); pointer.resize(1600, 1000)
        do('layout.switch', name='projects'); do('pane.focus', terminal='fixture/' + address)
        wait_for(lambda: jcall([app, 'status']).get('tab') == 'fixture/' + p['main']['tab'], 'initial remote focus')
        # Tabs restore each Space's panel choice after switching machines.
        # Open only after that native restore has rendered.
        time.sleep(.4)
        do('layout.select', stack='panel-body', child='project'); do('layout.show', id='panel')
        time.sleep(2); pointer.click(1565, 965)
        status = jcall([app, 'status'])
        check('Remote native panel has no host errors or overlays', not status.get('errors') and not status.get('overlays'))
        call([app, 'shot', str(output / 'tasks.png')])
        do('project.focus'); pointer.key('2'); pointer.key('Down'); pointer.key('Down'); pointer.key('Return')
        wait_for(lambda: jcall([app, 'status']).get('tab') == 'fixture/' + worker['tab'], 'remote Worker navigation')
        check('Native sidebar selects remote Worker despite a local address collision', True)
        time.sleep(.4)
        do('project.focus'); pointer.key('2'); pointer.key('Down'); pointer.key('Return')
        wait_for(lambda: jcall([app, 'status']).get('tab') == 'fixture/' + p['main']['tab'], 'remote Main navigation')
        check('Worker navigation returns to the remote project Main', True)
        time.sleep(.4)
        do('project.focus'); pointer.key('3'); pointer.key('Down'); pointer.key('Down'); pointer.key('Return')
        time.sleep(.7); call([app, 'shot', str(output / 'artifact.png')])
        do('pane.focus', terminal=address); time.sleep(.4)
        do('layout.select', stack='panel-body', child='project'); do('layout.show', id='panel'); time.sleep(.7)
        call([app, 'shot', str(output / 'local.png')])
        do('pane.focus', terminal='fixture/' + address); time.sleep(.7)
        # Cut only our byte-stream bridges. The server core and Main remain alive.
        gate.write_text('offline')
        time.sleep(.5)
        failed = remote(remote_cli + ['probe'], ok=False)
        check('Disconnected machine fails explicitly without local fallback', failed.returncode != 0)
        check('Disconnect does not terminate or replace the remote Main', jcall(['hc', 'get', address], env=server)['state'] == 'live')
        gate.unlink()
        wait_for(lambda: remote(remote_cli + ['probe'], ok=False).returncode == 0, 'reconnection')
        recovered = json.loads(remote(remote_cli + ['snapshot', '--terminal', address]).stdout)
        check('Reconnect reads the same Main, ledger and generation', recovered['project']['main']['id'] == p['main']['id'] and recovered['project']['main']['generation'] == p['main']['generation'] and recovered['ledgerHome'] == snapshot['ledgerHome'])
        wait_for(lambda: 'fixture/' + address in call([app, 'ls'], ok=False).stdout, 'reconnected layout')
        do('pane.focus', terminal='fixture/' + address); do('project.refresh'); time.sleep(1)
        call([app, 'shot', str(output / 'reconnected.png')])
        check('Reconnected native window has no host errors', not jcall([app, 'status']).get('errors'))
        for path in (desktop['panel'], desktop['tabs']):
            call([app, 'check', path])
        check('Installed native mods pass Herdr check', True)
        (output / 'result.json').write_text(json.dumps(dict(passed=len(checks), checks=checks, app=call([app, '--version']).stdout.strip(),
            core=call(['hc', '--version']).stdout.strip(), transport='real hc machine --via, loopback isolated cores; not SSH between physical hosts', synthetic=True), ensure_ascii=False, indent=2) + '\n')
    finally:
        gate.unlink(missing_ok=True)
        if pointer:
            pointer.close()
        if window:
            window.terminate()
            try: window.wait(timeout=10)
            except subprocess.TimeoutExpired: window.kill(); window.wait(timeout=5)
        for env in (client, second, server):
            call(['hc', 'server', 'stop'], env=env, ok=False)
        if display:
            display.terminate()
            try: display.wait(timeout=5)
            except subprocess.TimeoutExpired: display.kill(); display.wait(timeout=5)
        for name in ('window.log', 'display.log'):
            if (scratch / name).exists():
                shutil.copy2(scratch / name, output / name)
        print('Isolated verification files: ' + str(scratch), flush=True)


if __name__ == '__main__':
    os.chdir(ROOT)
    main()
