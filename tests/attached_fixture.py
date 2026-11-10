"""An existing native Agent fixture; receives a visible introduction, no LLM."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

root = Path(sys.argv[1])
print('Existing native Agent fixture (synthetic, no model)', flush=True)
print('\033]7501;state=idle:app=pi\033\\', end='', flush=True)
for line in sys.stdin:
    if ' context --project ' not in line:
        continue
    command = shlex.split(line.strip())
    if not command or command[0] != sys.executable:
        continue
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'Main / SuperAgent' in result.stdout
    prefix = command[:command.index('context')]
    project_id = command[-1]
    p = json.loads(subprocess.check_output(prefix + ['show', '--project', project_id], text=True))
    request = root / 'attached-request.json'
    request.write_text(json.dumps(dict(requestId='attached-update', op='todo.add', title='First task from existing Leader', sourceRef='Native fixture introduction')))
    result = subprocess.run(prefix + ['apply', '--project', project_id, '--revision', str(p['revision']), '--file', str(request)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    (root / 'attached-ready').write_text(json.dumps(dict(project=project_id, terminal=os.environ.get('HC_TERMINAL_ID'))))
    print('Project context loaded; durable task added through terminal identity.', flush=True)
    print('\033]7501;state=idle:app=pi\033\\', end='', flush=True)
