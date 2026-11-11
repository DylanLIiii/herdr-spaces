"""Immutable, manifest-backed publications stored independently of executions."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

from .store import ProjectError, file_hash, identifier, now, strings, text

KINDS = ('document', 'research', 'code-change', 'test-result', 'dataset-manifest', 'design')
TEXT_SUFFIXES = {'.md', '.txt', '.json', '.jsonl', '.csv', '.tsv', '.log', '.py', '.js', '.ts', '.sh', '.yaml', '.yml', '.toml', '.diff', '.patch', '.html', '.css', '.bib'}
MAX_TOTAL = 100 * 1024 * 1024


def relative(value):
    value = text(value, 'bundle member', 1000)
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or '\\' in value or '\0' in value or value != str(path) or value == '.':
        raise ProjectError('Bundle member must be a normalized relative path')
    return value


def digest(path):
    value = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def validate_claims(values):
    if not isinstance(values, list) or len(values) > 100:
        raise ProjectError('claims must be a bounded list')
    result = []
    for claim in values:
        if not isinstance(claim, dict):
            raise ProjectError('Invalid claim')
        sources = claim.get('sources', [])
        if not isinstance(sources, list) or not sources or len(sources) > 30:
            raise ProjectError('Each key claim needs source locators')
        validated = []
        for source in sources:
            if not isinstance(source, dict):
                raise ProjectError('Invalid source')
            validated.append(dict(reference=text(source.get('reference'), 'source reference', 2000),
                                  locator=text(source.get('locator'), 'source locator', 2000),
                                  accessedAt=text(source.get('accessedAt'), 'source access date', 80)))
        status = claim.get('verification', 'unverified')
        if status not in ('verified', 'unverified', 'contradicted'):
            raise ProjectError('Invalid claim verification')
        result.append(dict(id=identifier(claim.get('id')), text=text(claim.get('text'), 'claim'), sources=validated,
                           verification=status, note=text(claim.get('note'), 'verification note'),
                           limitations=strings(claim.get('limitations', []), 'limitations')))
    if len({claim['id'] for claim in result}) != len(result):
        raise ProjectError('Duplicate claim ids')
    return result


def publish(store, project, artifact_id, request):
    from .workspaces import artifact_root
    bundle = request['bundle']
    if not isinstance(bundle, dict):
        raise ProjectError('bundle must be an object')
    source = Path(text(bundle.get('root'), 'bundle root')).expanduser()
    if not source.is_absolute() or not source.is_dir():
        raise ProjectError('Bundle root must be an existing absolute directory')
    source = source.resolve()
    files = bundle.get('files')
    if not isinstance(files, list) or not files or len(files) > 200:
        raise ProjectError('Bundle needs 1–200 explicitly listed files')
    entrypoint = relative(bundle.get('entrypoint', 'brief.md'))
    kind = request.get('kind', 'document')
    if kind not in KINDS:
        raise ProjectError('Unknown artifact kind')
    inventory, total, seen = [], 0, set()
    for item in files:
        if not isinstance(item, dict):
            raise ProjectError('Bundle files need path and role')
        name = relative(item.get('path'))
        if name == 'manifest.json' or name in seen:
            raise ProjectError('Duplicate or reserved bundle member')
        seen.add(name)
        candidate = source / name
        if any(part.is_symlink() for part in [candidate, *candidate.parents] if part != source and source in part.parents):
            raise ProjectError('Bundle members may not use symlinks')
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(source) or not resolved.is_file():
            raise ProjectError('Bundle member escapes the source directory or is not a file')
        size = resolved.stat().st_size
        total += size
        if total > MAX_TOTAL:
            raise ProjectError('Bundle exceeds 100 MiB; publish a bounded external-data manifest instead')
        inventory.append(dict(path=name, role=text(item.get('role', 'attachment'), 'file role', 80),
                              size=size, sha256=digest(resolved)))
    if entrypoint not in seen:
        raise ProjectError('Bundle entrypoint must be a listed file')
    workflow = bundle.get('workflow')
    if kind == 'research':
        if workflow not in ('deepresearch', 'autoresearch'):
            raise ProjectError('Research bundles need a workflow')
        roles = {entry['role'] for entry in inventory}
        required = {'plan', 'draft', 'cited', 'brief', 'provenance'} if workflow == 'deepresearch' else {'summary', 'benchmark', 'iterations', 'changelog', 'brief', 'provenance'}
        if required - roles:
            raise ProjectError('Research bundle lacks required files: ' + ', '.join(sorted(required - roles)))
    claims = validate_claims(bundle.get('claims', []))
    external = bundle.get('external', [])
    if not isinstance(external, list) or len(external) > 100:
        raise ProjectError('external must be a bounded manifest')
    locations = []
    for entry in external:
        if not isinstance(entry, dict) or type(entry.get('size')) is not int or entry['size'] < 0:
            raise ProjectError('External data needs a nonnegative byte size')
        if entry.get('status') not in ('verified', 'unverified', 'unavailable'):
            raise ProjectError('External data needs an explicit verification status')
        locations.append(dict(location=text(entry.get('location'), 'external location', 2000),
                              contentId=text(entry.get('contentId'), 'content identifier', 300),
                              size=entry['size'], status=entry['status'],
                              note=text(entry.get('note'), 'external verification note')))
    manifest = dict(formatVersion=1, id=artifact_id, kind=kind, workflow=workflow, entrypoint=entrypoint,
                    files=inventory, claims=claims, external=locations)
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    root = artifact_root(store, project) / 'published'
    root.mkdir(parents=True, exist_ok=True)
    final = root / artifact_id
    if final.exists():
        if not (final / 'manifest.json').is_file() or (final / 'manifest.json').read_text() != encoded:
            raise ProjectError('Publication id already contains different content; choose a new version id')
        verify_manifest(final / 'manifest.json')
    else:
        stage = Path(tempfile.mkdtemp(prefix='.publish-', dir=root))
        try:
            for entry in inventory:
                target = stage / entry['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / entry['path'], target)
                if digest(target) != entry['sha256']:
                    raise ProjectError('Source changed while publishing; retry with stable files')
                with target.open('rb') as stream:
                    os.fsync(stream.fileno())
            (stage / 'manifest.json').write_text(encoded)
            with (stage / 'manifest.json').open('rb') as stream:
                os.fsync(stream.fileno())
            stage.rename(final)
            directory_fd = os.open(root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if stage.exists():
                shutil.rmtree(stage)  # Only this attempt's unpublished temporary directory.
    return dict(path=str(final / 'manifest.json'), storage='managed', entrypoint=entrypoint,
                kind=kind, workflow=workflow, claims=claims, members=len(inventory))


def verify_manifest(path):
    path = Path(path)
    manifest = json.loads(path.read_text())
    if manifest.get('formatVersion') != 1:
        raise ProjectError('Unsupported artifact manifest')
    root = path.parent.resolve()
    for entry in manifest['files']:
        member = root / relative(entry['path'])
        if not member.resolve(strict=True).is_relative_to(root) or member.is_symlink() or digest(member) != entry['sha256']:
            raise ProjectError('Published artifact content changed or escaped its root')
    return manifest


def verify(artifact):
    if file_hash(artifact['path']) != artifact['sha256']:
        raise ProjectError('Artifact changed since registration; register and review a new version')
    if artifact.get('storage') == 'managed':
        verify_manifest(artifact['path'])


def preview(artifact, member=None, offset=0):
    if type(offset) is not int or offset < 0:
        raise ProjectError('Preview offset must be a nonnegative byte offset')
    path = Path(artifact['path'])
    metadata = {}
    changed = file_hash(path) != artifact['sha256']
    if artifact.get('storage') == 'managed':
        # Never trust a changed manifest to select a new file for preview.
        if changed:
            return dict(path=str(path), changed=True, text='', truncated=False, error='产物清单已变更，请重新发布并核验。')
        manifest = json.loads(path.read_text())
        name = relative(member or manifest['entrypoint'])
        entry = next((entry for entry in manifest['files'] if entry['path'] == name), None)
        if not entry:
            raise ProjectError('Unknown artifact member')
        candidate = path.parent / name
        if not candidate.resolve(strict=True).is_relative_to(path.parent.resolve()) or candidate.is_symlink():
            raise ProjectError('Artifact member escaped its publication directory')
        path = candidate
        changed = digest(path) != entry['sha256']
        metadata = dict(files=manifest['files'], claims=manifest['claims'], external=manifest['external'], member=name)
    elif member:
        raise ProjectError('External file references have no bundle members')
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return dict(path=str(path), changed=changed, text='', truncated=False, previewType='binary',
                    message='此文件不是文本。请使用项目机器上的对应阅读工具。', **metadata)
    with path.open('rb') as source:
        source.seek(offset)
        raw = source.read(64001)
    data = raw[:64000]
    # Keep subsequent UTF-8 pages aligned without losing bytes.
    if len(raw) > 64000:
        try:
            data.decode('utf-8')
        except UnicodeDecodeError as exc:
            if exc.end == len(data):
                data = data[:exc.start]
    return dict(path=str(path), changed=changed, text=data.decode('utf-8', errors='replace'),
                truncated=len(raw) > 64000, offset=offset,
                nextOffset=offset + len(data) if len(raw) > 64000 else None, previewType='text', **metadata)


def search(project, query):
    query = text(query, 'search query', 300).casefold()
    results = []
    for artifact in project['artifacts']:
        haystack = ' '.join(str(artifact.get(key, '')) for key in ('title', 'sourceRef', 'kind', 'reviewNote', 'dispositionNote'))
        haystack += json.dumps(artifact.get('claims', []), ensure_ascii=False)
        try:
            # Search bounded text on disk; this is an index-free convenience, not new evidence.
            path = Path(artifact['path'])
            if artifact.get('storage') == 'managed':
                if file_hash(path) != artifact['sha256']:
                    continue
                manifest = json.loads(path.read_text())
                root = path.parent.resolve()
                path = root / relative(manifest['entrypoint'])
                if not path.resolve(strict=True).is_relative_to(root) or path.is_symlink():
                    continue
            if path.suffix.lower() in TEXT_SUFFIXES:
                with path.open('r', errors='replace') as source:
                    haystack += source.read(200000)
        except (OSError, ValueError, ProjectError):
            pass
        if query in haystack.casefold():
            results.append(artifact)
    return results
