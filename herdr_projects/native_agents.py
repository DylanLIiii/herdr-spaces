"""Native backend integration. Core owns terminals; adapters report real events."""
import hashlib
import json
import os
from pathlib import Path

from .store import ProjectError

STATUS_PLUGIN = Path(__file__).resolve().parent / 'integrations/opencode-status'


def environment(run, inherited, argv, tty=None):
    env, command = dict(inherited), list(argv)
    execution = run.get('execution') or {}
    if execution.get('backend') != 'opencode':
        return env, command
    # Custom argv is authoritative; only bridge the supported private mini mode.
    if 'mini' not in command or '--standalone' not in command or '--server' in command:
        return env, command
    if '--session' in command:
        session = command[command.index('--session') + 1]
    elif '-s' in command:
        session = command[command.index('-s') + 1]
    else:
        session = 'ses_' + hashlib.sha256(run['id'].encode()).hexdigest()[:26]
        command += ['--session', session]
    try:
        config = json.loads(env.get('OPENCODE_CONFIG_CONTENT') or '{}')
    except ValueError as exc:
        raise ProjectError('OPENCODE_CONFIG_CONTENT is invalid; native status adapter cannot merge it') from exc
    if not isinstance(config, dict) or not isinstance(config.get('plugins', []), list):
        raise ProjectError('OpenCode inline configuration needs an object and a plugins array')
    config['plugins'] = [*config.get('plugins', []), str(STATUS_PLUGIN)]
    env.update(OPENCODE_CONFIG_CONTENT=json.dumps(config), HERDR_SPACES_SESSION_ID=session,
               HERDR_SPACES_STATUS_TTY=tty or os.ttyname(0))
    return env, command
