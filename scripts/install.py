#!/usr/bin/env python3
"""Install personal copies, or only the runtime on a project's machine."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent


def runtime_bundle():
    names = ['project.py', 'LICENSE'] + ['herdr_projects/' + name for name in
        ('__init__.py', 'store.py', 'runtime.py', 'cli.py', 'onboarding.py', 'manager.py',
         'schema.py', 'coordination.py', 'setup_flow.py', 'teams.py', 'workspaces.py', 'artifacts.py',
         'skills/herdr-spaces-setup/SKILL.md',
         'skills/project-manager/SKILL.md', 'skills/project-manager/references/subagents.md')]
    files = {name: (ROOT / name).read_text() for name in names}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(files=files, sha256=digest)


def install(home, bin_dir, data_home, name='projects', *, runtime_only=False, registry_dir=None, remote_name=None):
    remote_name = remote_name or name
    if not all(re.fullmatch(r'[a-z][a-z0-9-]{0,39}', value) for value in (name, remote_name)):
        raise ValueError('Invalid installation name')
    home, bin_dir, data_home = [Path(p).expanduser().resolve() for p in (home, bin_dir, data_home)]
    registry = Path(registry_dir or Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'herdr-spaces/runtimes').expanduser().resolve()
    panel = 'project' if name == 'projects' else name + '-panel'
    tabs = name + '-tabs'
    agents = name + '-agents'
    setup = 'project-setup' if name == 'projects' else name + '-setup'
    binary = bin_dir / ('herdr-project' if name == 'projects' else name + '-project')
    runtime = home / 'projects-runtime' / name
    discovery = registry / (name + '.json')
    panel_path, tabs_path, layout_path = home / 'mods' / panel, home / 'mods' / tabs, home / 'layouts' / (name + '.json')
    agents_path, setup_path = home / 'mods' / agents, home / 'mods' / setup
    targets = [runtime, binary, discovery] + ([] if runtime_only else [panel_path, tabs_path, agents_path, setup_path, layout_path])
    for target in targets:
        if target.exists() or target.is_symlink():
            raise FileExistsError(f'Already exists: {target}. Existing installs are never overwritten. Use --name for a separate preview.')
    owned = []
    try:
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.mkdir()  # Atomic reservation, fails if another installer won.
        owned.append(runtime)
        shutil.copy2(ROOT / 'project.py', runtime / 'project.py')
        shutil.copy2(ROOT / 'LICENSE', runtime / 'LICENSE')
        shutil.copytree(ROOT / 'herdr_projects', runtime / 'herdr_projects', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copy2(ROOT / 'scripts/bootstrap.py', runtime / 'bootstrap.py')
        (runtime / 'runtime-bundle.json').write_text(json.dumps(runtime_bundle()))
        command = [sys.executable, str(runtime / 'project.py'), '--home', str(data_home)]
        manifest = dict(name=name, home=str(home), dataHome=str(data_home), binary=str(binary),
                        runtime=str(runtime), discovery=str(discovery), command=command, runtimeOnly=runtime_only, remoteName=remote_name)
        if not runtime_only:
            for mod, target in [('project', panel_path), ('projects-tabs', tabs_path), ('projects-agents', agents_path), ('project-setup', setup_path)]:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.mkdir()
                owned.append(target)
                for source in (ROOT / 'mods' / mod).iterdir():
                    if source.suffix not in ('.js', '.json', '.svg') or source.name == 'jsconfig.json':
                        continue
                    content = source.read_text().replace('mods/project/', f'mods/{panel}/').replace('mods/projects-tabs/', f'mods/{tabs}/').replace('../project/', f'../{panel}/')
                    (target / source.name).write_text(content)
                if mod == 'project-setup':
                    # GPUI isolates module roots; each mod needs its own copy.
                    shutil.copy2(ROOT / 'mods/project/transport.js', target / 'transport.js')
                shutil.copy2(ROOT / 'docs/LICENSE.herdr-app', target / 'LICENSE.herdr-app')
                for notice in ('LICENSE', 'THIRD-PARTY-NOTICES.md'):
                    shutil.copy2(ROOT / notice, target / notice)
            layout = json.loads((ROOT / 'layouts/projects.json').read_text())
            config = dict(python=sys.executable, entry=str(runtime / 'project.py'), dataHome=str(data_home),
                          remoteName=remote_name, panelMod=panel, setupMod=setup, agentsMod=agents,
                          bundle=str(runtime / 'runtime-bundle.json'), bootstrap=str(runtime / 'bootstrap.py'))
            def walk(node):
                content = node.get('content', {})
                if content.get('mod') == 'project':
                    content.update(mod=panel, props=config)
                if content.get('mod') in ('agents', 'projects-agents'):
                    content.update(mod=agents, props=config)
                if content.get('mod') == 'projects-tabs':
                    content['mod'] = tabs
                for child in node.get('children', []):
                    walk(child)
            walk(layout)
            layout_path.parent.mkdir(parents=True, exist_ok=True)
            with layout_path.open('x') as f:
                owned.append(layout_path); f.write(json.dumps(layout, indent=2) + '\n')
            manifest.update(panel=str(panel_path), tabs=str(tabs_path), agents=str(agents_path), setup=str(setup_path), layout=str(layout_path))
        bin_dir.mkdir(parents=True, exist_ok=True)
        with binary.open('x') as f:
            owned.append(binary); f.write('#!/bin/sh\nexec ' + shlex.join(command) + ' "$@"\n')
        binary.chmod(0o755)
        registry.mkdir(parents=True, exist_ok=True)
        with discovery.open('x') as f:
            owned.append(discovery); f.write(json.dumps(dict(protocolVersion=1, command=command), indent=2) + '\n')
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
    parser.add_argument('--remote-name', help='Keep the existing remote runtime registration name when installing a new desktop layout')
    parser.add_argument('--runtime-only', action='store_true', help='Install CLI/runtime on the project machine without desktop mods or layouts')
    parser.add_argument('--registry-dir', help='Override discovery directory; the default is the target machine XDG config/herdr-spaces/runtimes')
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.home, args.bin_dir, args.data_home, args.name,
                                 runtime_only=args.runtime_only, registry_dir=args.registry_dir, remote_name=args.remote_name), indent=2))
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
