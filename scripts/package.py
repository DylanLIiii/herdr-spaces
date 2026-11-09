#!/usr/bin/env python3
"""Build a source/install archive without local state, logs or credentials."""
import argparse
import gzip
import hashlib
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / 'dist/herdr-spaces-0.1.0.tar.gz'))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    paths = [ROOT / name for name in ('README.md', 'LICENSE', 'THIRD-PARTY-NOTICES.md', 'package.json', 'project.py', '.gitignore')]
    for folder, extensions in [('herdr_projects', {'.py'}), ('scripts', {'.py'}), ('tests', {'.py', '.js'}),
                               ('mods', {'.js', '.json', '.svg'}), ('layouts', {'.json'}), ('docs', {'.md', '.png', '.json', '.herdr-app'})]:
        paths.extend(p for p in (ROOT / folder).rglob('*') if p.is_file() and p.suffix in extensions and '__pycache__' not in p.parts)
    paths = sorted(set(paths))
    with output.open('wb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed, tarfile.open(fileobj=compressed, mode='w') as archive:
        for path in paths:
            info = archive.gettarinfo(str(path), 'herdr-spaces/' + str(path.relative_to(ROOT)))
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ''
            with path.open('rb') as source:
                archive.addfile(info, source)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + '.sha256').write_text(digest + '  ' + output.name + '\n')
    print(f'{output}\n{len(paths)} files, {output.stat().st_size} bytes\nSHA256 {digest}')


if __name__ == '__main__':
    main()
