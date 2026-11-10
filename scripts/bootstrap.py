#!/usr/bin/env python3
"""Install the desktop's bundled runtime on the selected project machine.

Called only by an explicit setup action, with a source bundle as argv. No network,
no shell interpolation, no project data copy and no modification of Agent config.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def prepare(name, bundle):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', name):
        raise ValueError('Invalid installation name')
    files = bundle['files']
    allowed = {'project.py', 'LICENSE', 'herdr_projects/__init__.py', 'herdr_projects/store.py',
               'herdr_projects/runtime.py', 'herdr_projects/cli.py', 'herdr_projects/onboarding.py'}
    if set(files) != allowed or any(not isinstance(v, str) for v in files.values()):
        raise ValueError('Invalid runtime bundle')
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if bundle.get('sha256') != digest:
        raise ValueError('Runtime bundle checksum mismatch')
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'herdr-spaces/runtimes'
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    config.mkdir(parents=True, exist_ok=True)
    registration = config / (name + '.json')
    with (config / (name + '.lock')).open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = str(data / 'herdr-projects')
        if registration.exists():
            previous = json.loads(registration.read_text())
            command = previous.get('command')
            if not isinstance(command, list) or not command or not all(isinstance(s, str) for s in command):
                raise ValueError('Invalid existing runtime registration; inspect before replacing')
            result = subprocess.run(command + ['probe'], capture_output=True, text=True, timeout=10)
            if result.returncode:
                raise ValueError('Existing runtime cannot be inspected; it was not replaced')
            probe = json.loads(result.stdout)
            ledger = probe['ledgerHome']
            if not Path(ledger).is_absolute():
                raise ValueError('Existing ledger path is invalid')
            if {'leader-bind', 'core-command-discovery'}.issubset(probe.get('capabilities', [])):
                return dict(prepared=False, command=command, ledgerHome=ledger)
        target = data / 'herdr-spaces/runtime' / name / digest[:20]
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            staging = Path(tempfile.mkdtemp(prefix='.prepare-', dir=target.parent))
            try:
                for relative, content in files.items():
                    path = staging / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content)
                staging.rename(target)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
        for relative, content in files.items():
            if (target / relative).read_text() != content:
                raise ValueError('Existing runtime files changed; no files were overwritten')
        command = [sys.executable, str(target / 'project.py'), '--home', ledger]
        check = subprocess.run(command + ['probe'], capture_output=True, text=True, timeout=10, check=True)
        if not {'leader-bind', 'core-command-discovery'}.issubset(json.loads(check.stdout).get('capabilities', [])):
            raise ValueError('Bundled runtime does not support Leader setup')
        descriptor, temporary = tempfile.mkstemp(prefix='.' + name, dir=config)
        try:
            with os.fdopen(descriptor, 'w') as stream:
                json.dump(dict(protocolVersion=1, command=command), stream)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, registration)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return dict(prepared=True, command=command, ledgerHome=ledger)


if __name__ == '__main__':
    try:
        print(json.dumps(prepare(sys.argv[1], json.loads(sys.argv[2]))))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps(dict(code='prepare_failed', message=str(exc))), file=sys.stderr)
        raise SystemExit(1)
