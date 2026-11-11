"""Project-local PM reading access and SubAgent launch preferences."""
from pathlib import Path

from .store import ProjectError, text
from .teams import BACKENDS

BUILTIN_SKILL = Path(__file__).resolve().parent / 'skills/project-manager/SKILL.md'


def settings(project):
    return dict(pmSkill=project.get('pmSkill') or str(BUILTIN_SKILL),
                subAgent=project.get('subAgent') or dict(backend='pi', model=None))


def configure(project, pm_skill=None, backend=None, model=None):
    """Validate before binding; omitted values preserve existing preferences."""
    result = settings(project)
    if pm_skill is not None:
        if pm_skill:
            path = Path(pm_skill).expanduser()
            if not path.is_absolute():
                raise ProjectError('Project Manager Skill 必须是项目机器上的绝对路径。')
            if path.is_dir():
                path = path / 'SKILL.md'
            path = path.resolve(strict=True)
            if not path.is_file():
                raise ProjectError('Project Manager Skill 必须是可读取的文件。')
            path.read_text(encoding='utf-8')
            result['pmSkill'] = str(path)
        else:
            result['pmSkill'] = str(BUILTIN_SKILL)
    agent = dict(result['subAgent'])
    if backend is not None:
        if backend not in BACKENDS:
            raise ProjectError('工具必须是 pi、claude、codex、opencode 或 feynman。')
        # A model name belongs to the selected backend, not all backends.
        if backend != agent['backend']:
            agent['model'] = None
        agent['backend'] = backend
    if model is not None:
        agent['model'] = text(model, 'model', 300) if model else None
    result['subAgent'] = agent
    return result


def skill_file(project, resource=None):
    entry = Path(settings(project)['pmSkill']).resolve(strict=True)
    if resource is None:
        return entry
    relative = Path(resource)
    if relative.is_absolute():
        raise ProjectError('Skill resource 必须是相对 Skill 目录的路径。')
    target = (entry.parent / relative).resolve(strict=True)
    if not target.is_relative_to(entry.parent) or not target.is_file():
        raise ProjectError('Skill resource 必须位于已配置的 Skill 目录内。')
    return target


def read_skill(project, resource=None):
    # Deliberately no summary, truncation or extension filter. Referenced text
    # resources can be read with the same command as the entry point.
    return skill_file(project, resource).read_text(encoding='utf-8')


def list_resources(project):
    root = skill_file(project).parent
    return sorted(str(p.relative_to(root)) for p in root.rglob('*')
                  if p.is_file() and p.resolve().is_relative_to(root))


def worker_command(project, backend=None, model=None, custom=None, profile=None):
    from .runtime import command
    preferences = settings(project)['subAgent']
    selected = profile['backend'] if profile else backend or preferences['backend']
    selected_model = profile.get('model') if profile else model if model is not None else (preferences.get('model') if selected == preferences['backend'] else None)
    if custom is not None:
        if model is not None:
            raise ProjectError('使用 --command-json 时，请在 argv 中指定模型。')
        return command(custom, selected)
    # Herdr requires per-terminal Codex processes so commands keep their own
    # terminal identity instead of inheriting a shared daemon's environment.
    if selected == 'opencode':
        argv = ['opencode', '--standalone', 'mini']
    elif selected == 'codex':
        argv = ['codex', '--no-daemon']
    elif selected == 'feynman':
        argv = ['feynman', '--new-session']
    else:
        argv = [selected]
    if selected_model:
        argv += ['--model', text(selected_model, 'model', 300)]
    if selected == 'opencode':
        argv += ['--prompt']
    if selected == 'feynman':
        argv += [profile.get('workflow', 'deepresearch') if profile else 'chat']
    return command(argv + ['{context}'], selected)
