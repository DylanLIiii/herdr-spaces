"""Bind an existing native terminal as a project's Leader on its own machine."""
import os
from pathlib import Path
import shlex
import shutil

from . import runtime, manager
from .store import ProjectError, identifier, now, text, uid


def terminal_info(address):
    identifier(address)  # A remote prefix never belongs in the target ledger.
    value = runtime.hc(['get', address, '--json'])
    if value.get('address') != address or value.get('state') != 'live':
        raise ProjectError('此终端已结束，请选择仍在运行的 Agent 终端。')
    return value


def setup(store, address):
    scopes = runtime.connected_scopes()
    terminal = terminal_info(address)
    cwd = terminal.get('foreground', {}).get('cwd') or terminal.get('cwd')
    projects = [store.public(store.get(row['id'])) for row in store.snapshot()['projects']]
    return dict(protocolVersion=1, coreScope=scopes[0], terminal=address,
                cwd=cwd, suggestedName=Path(cwd).name if cwd else '', newProjectId=uid('project'),
                binding=store.snapshot(address, scopes=scopes)['binding'],
                defaults=manager.settings({}),
                tools=[dict(id=backend, available=bool(manager.executable(backend))) for backend in manager.BACKENDS],
                projects=[{k: p[k] for k in ('id', 'name', 'goal', 'cwd', 'main', 'setup', 'configuration')} | manager.settings(p) for p in projects])


def bind(store, address, core_scope, project_id, name=None, goal=None, cwd=None,
         replace_generation=None, pm_skill=None, worker_backend=None, worker_model=None):
    identifier(project_id)
    scopes = runtime.connected_scopes()
    if core_scope != scopes[0]:
        raise ProjectError('机器连接已改变，请重新打开项目设置。')
    terminal = terminal_info(address)
    # Two clients selecting the same terminal/project cannot create two owners.
    with runtime.lock(store, 'bind-' + address), runtime.lock(store, project_id + '-main-launch'), runtime.lock(store, project_id + '-intro'):
        previous = store.snapshot(address, scopes=scopes)
        if previous['binding'] and (previous['binding']['project_id'] != project_id or previous['binding']['role'] != 'main'):
            raise ProjectError('此终端已属于另一个项目或执行任务，不能再指定为 Leader。')
        exists = any(p['id'] == project_id for p in store.snapshot()['projects'])
        preferences = manager.configure(store.get(project_id) if exists else {}, pm_skill, worker_backend, worker_model)
        if not exists:
            if replace_generation is not None:
                raise ProjectError('项目已改变，请重新打开项目设置。')
            if not name or not goal or not cwd:
                raise ProjectError('请填写项目名称、目标和目录。')
            store.create(project_id, name, goal, cwd)
        with store.transaction():
            p = store.get(project_id)
            main = p['main']
            if replace_generation is not None and main['generation'] != replace_generation:
                raise ProjectError('PM 已改变，请重新打开项目设置后再绑定。')
            if main.get('scope') and main['scope'] not in scopes:
                raise ProjectError('请在项目原来的 Core 上重新绑定 PM。')
            same = main.get('terminal') == address and main.get('scope') in scopes and main['state'] == 'running'
            old_terminal = None
            changed = any(p.get(k) != v for k, v in preferences.items())
            if not same:
                if main['state'] not in ('inactive', 'exited') and replace_generation is None:
                    raise ProjectError('此项目已有 PM。重新绑定需要明确指定当前 generation。')
                if previous['binding'] and replace_generation is None:
                    raise ProjectError('恢复旧终端需要明确指定当前 generation。')
                terminal = terminal_info(address)
                old_terminal = main.get('terminal')
                old_scope = main.get('scope')
                # Revoke the previous routing and credentials in the same commit.
                if old_terminal:
                    store.db.execute('DELETE FROM bindings WHERE scope=? AND terminal=? AND project_id=? AND role=?',
                                     (old_scope, old_terminal, project_id, 'main'))
                labels = terminal.get('labels') or {}
                main.update(generation=main['generation'] + 1, token=uid('token'), state='running', mode='attached',
                            terminal=address, scope=scopes[0], startedAt=now(),
                            space=labels.get('herdr.space'), tab=labels.get('herdr.tab'), notice=None)
                for key in ('command', 'exitCode', 'endedAt', 'reconciled'):
                    main.pop(key, None)
                store.bind(project_id, address, scopes[0], 'main')
                from .coordination import handoff
                handoff(store, p)
            if not same or changed:
                p.update(preferences)
                main['notice'] = None
                p['revision'] += 1
                store.save(p)
                store.event(p, uid('bind'), '', main['id'], dict(op='main.rebind' if old_terminal else 'main.configure' if same else 'main.bind',
                            terminal=address, previousTerminal=old_terminal, generation=main['generation'], **preferences))
        warning = None
        try:
            runtime.hc(['label', address, 'projects.project=' + project_id, 'projects.role=main', 'projects.name=' + p['name']])
        except ProjectError:
            warning = '项目已绑定，左侧标记暂未更新。刷新后可重试，不会重复创建 Leader。'
        if old_terminal and old_terminal != address:
            try:
                runtime.hc(['label', old_terminal, 'projects.role=former-main'])
            except ProjectError:
                warning = 'PM 已重新绑定且旧凭据已失效，旧终端的 Leader 标记暂未清除。'
        return dict(project=store.public(p), warning=warning)


def attached_identity(store):
    address = os.environ.get('HC_TERMINAL_ID')
    if not address:
        return None
    scopes = runtime.connected_scopes()
    snap = store.snapshot(address, scopes=scopes)
    p, binding = snap['project'], snap['binding']
    if not p or not binding or binding['role'] != 'main':
        return None
    # Only explicit attachment enables terminal-derived credentials. Managed
    # runs still require their inherited token and never fall back here.
    main = store.get(p['id'])['main']
    if main.get('mode') != 'attached' or main['state'] != 'running' or main['terminal'] != address or main['scope'] != scopes[0]:
        return None
    terminal_info(address)
    return dict(project=p['id'], role='main', main=main['id'], generation=main['generation'], token=main['token'], run=None)


def introduction(store, project_id):
    p = store.get(project_id)
    return f'''你已被用户指定为项目 {p['name']} 的 Project Leader（Main）。保持当前原生会话。
项目目标：{p['goal'][:1500]}
用户已授权你完整读取本项目配置的 Project Manager Skill 及其目录内的引用文件。
请先执行以下命令，读取完整 Skill、引用资源、项目记录与维护接口，再继续工作：
{runtime.cli_prefix(store)} skill --project {shlex.quote(project_id)}
{runtime.cli_prefix(store)} skill --project {shlex.quote(project_id)} --list
{runtime.cli_prefix(store)} context --project {shlex.quote(project_id)}
激活本项目的首次配置 Skill（自定义 PM Skill 也使用此入口）：
{runtime.cli_prefix(store)} skill --project {shlex.quote(project_id)} --setup
按 Skill 引用使用 skill --resource 相对路径读取全文。读取 show 中的 setup 状态：尚未邀请且用户未同意时，由你询问是否现在开始配置；已同意、已暂缓或接任时续接记录，不重复询问。
此绑定只建立 PM 身份；用户同意开始后才检查环境和推荐 SubAgent 配置。完成绑定不等于完成配置。
任务变化通过此项目 CLI 维护；不要重复创建 Leader。此消息只建立项目职责，不新增合并、部署或派发授权。'''


def notify(store, project_id, core_scope, generation):
    """One visible introduction, only through Core's atomic idle guard.

    A reserved/uncertain send is never replayed automatically. A separate user
    action can retry only when no send was made because the terminal was busy.
    """
    scopes = runtime.connected_scopes()
    if core_scope != scopes[0]:
        raise ProjectError('机器连接已改变，请刷新项目。')
    with runtime.lock(store, project_id + '-intro'):
        p = store.get(project_id)
        main = p['main']
        if main['state'] != 'running' or main.get('scope') != scopes[0] or main['generation'] != generation:
            raise ProjectError('Leader 已改变，请刷新项目。')
        if main.get('notice') and main['notice']['state'] in ('sent', 'uncertain', 'sending'):
            return dict(state=main['notice']['state'], message=introduction(store, project_id))
        terminal = terminal_info(main['terminal'])
        status = terminal.get('status') or {}
        if status.get('state') != 'idle' or not status.get('app'):
            return dict(state='waiting', message=introduction(store, project_id))
        with store.transaction():
            p = store.get(project_id)
            if p['main']['generation'] != generation:
                raise ProjectError('Leader 已改变，请刷新项目。')
            p['main']['notice'] = dict(state='sending', at=now())
            store.save(p)
        state = 'sent'
        try:
            runtime.hc(['send', main['terminal'], introduction(store, project_id), '--if', 'idle', '--json'])
        except ProjectError:
            # Core may have delivered despite a lost reply; never send twice.
            state = 'uncertain'
        with store.transaction():
            p = store.get(project_id)
            if p['main']['generation'] == generation:
                p['main']['notice'] = dict(state=state, at=now())
                store.save(p)
        return dict(state=state, message=introduction(store, project_id))
