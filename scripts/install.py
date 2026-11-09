#!/usr/bin/env python3
"""Install personal copies; never modify a shipped mod, layout or user settings."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent


def install(home, bin_dir, data_home, name='projects'):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', name):
        raise ValueError('Invalid installation name')
    home, bin_dir, data_home = [Path(p).expanduser().resolve() for p in (home, bin_dir, data_home)]
    panel = 'project' if name == 'projects' else name + '-panel'
    tabs = name + '-tabs'
    binary = 'herdr-project' if name == 'projects' else name + '-project'
    runtime = home / 'projects-runtime' / name
    targets = [home / 'mods' / panel, home / 'mods' / tabs, home / 'layouts' / (name + '.json'), runtime, bin_dir / binary]
    for target in targets:
        if target.exists() or target.is_symlink():
            raise FileExistsError(f'Already exists: {target}. Existing installs are never overwritten. Use --name for a separate preview.')
    owned = []
    try:
        for mod, target in [('project', targets[0]), ('projects-tabs', targets[1])]:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.mkdir()  # Atomic reservation, fails if another installer won.
            owned.append(target)
            for source in (ROOT / 'mods' / mod).iterdir():
                if source.suffix not in ('.js', '.json', '.svg'):
                    continue
                content = source.read_text().replace('mods/project/', f'mods/{panel}/').replace('mods/projects-tabs/', f'mods/{tabs}/')
                (target / source.name).write_text(content)
            shutil.copy2(ROOT / 'docs/LICENSE.herdr-app', target / 'LICENSE.herdr-app')
            for notice in ('LICENSE', 'THIRD-PARTY-NOTICES.md'):
                shutil.copy2(ROOT / notice, target / notice)
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.mkdir()
        owned.append(runtime)
        shutil.copy2(ROOT / 'project.py', runtime / 'project.py')
        shutil.copy2(ROOT / 'LICENSE', runtime / 'LICENSE')
        shutil.copytree(ROOT / 'herdr_projects', runtime / 'herdr_projects', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        layout = json.loads((ROOT / 'layouts/projects.json').read_text())
        def walk(node):
            content = node.get('content', {})
            if content.get('mod') == 'project':
                content.update(mod=panel, props=dict(python=sys.executable, entry=str(runtime / 'project.py'), dataHome=str(data_home)))
            if content.get('mod') == 'projects-tabs':
                content['mod'] = tabs
            for child in node.get('children', []):
                walk(child)
        walk(layout)
        targets[2].parent.mkdir(parents=True, exist_ok=True)
        with targets[2].open('x') as f:
            owned.append(targets[2]); f.write(json.dumps(layout, indent=2) + '\n')
        bin_dir.mkdir(parents=True, exist_ok=True)
        with targets[4].open('x') as f:
            owned.append(targets[4]); f.write('#!/bin/sh\nexec ' + shlex.join([sys.executable, str(runtime / 'project.py'), '--home', str(data_home)]) + ' "$@"\n')
        targets[4].chmod(0o755)
        manifest = dict(name=name, home=str(home), dataHome=str(data_home), binary=str(targets[4]),
                        panel=str(targets[0]), tabs=str(targets[1]), layout=str(targets[2]), runtime=str(runtime))
        (runtime / 'install.json').write_text(json.dumps(manifest, indent=2) + '\n')
        return manifest
    except BaseException:
        # Roll back only paths atomically created by this invocation.
        for path in reversed(owned):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', default=os.environ.get('HERDR_APP_HOME', str(Path.home() / '.config/herdr-app')))
    parser.add_argument('--bin-dir', default=str(Path.home() / '.local/bin'))
    parser.add_argument('--data-home', default=os.environ.get('HERDR_PROJECTS_HOME', str(Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'herdr-projects')))
    parser.add_argument('--name', default='projects')
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.home, args.bin_dir, args.data_home, args.name), indent=2))
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
