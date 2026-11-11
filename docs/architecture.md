# 数据、身份与恢复

## 实现范围

Projects 是一个独立插件工程：Python CLI 保存 SQLite 账本并通过现有 hc CLI 启动程序；原生 GPUI mod 调用只读命令显示记录。Herdr app/core 源码、共享 API、内置布局都未修改。

默认数据目录为 `${XDG_DATA_HOME:-~/.local/share}/herdr-projects`。可用 `HERDR_PROJECTS_HOME` 或 `--home` 指定。表结构版本保存在 SQLite `user_version`，当前为 2；事务迁移保留旧项目、身份、修订与证据。更高版本不会被旧程序静默打开。SQLite 使用 WAL、写事务和唯一约束。备份时使用 SQLite backup API；不要仅复制运行中的主库文件而遗漏 WAL。

## 项目与执行

一个 Project 的 Main id 在创建时确定，终身归属于该项目。当前 terminal、core scope、generation、launch token 和 process state 独立于这个 id。Main 重启提升 generation；界面始终跟随显式 terminal binding，不根据仓库目录猜项目。0.2 的新执行使用 `hc server status` 返回的持久 Core id 作为 scope；0.1 的环境 scope 保留兼容读取，多个匹配则拒绝猜测。

0.3 还支持 `bind` 将已有原生终端指定为 Leader，保持该终端和会话。Attached 模式通过 Core id / terminal 绑定解析 CLI 身份；Managed 模式继续使用代次 token。绑定和介绍状态分别记录，不能把绑定视为 Agent 已收到规则。显式重新绑定校验 generation，并在同一事务中删除旧 binding、提升 generation、轮换 token、更新终端和保存配置。Main id、项目历史与 Worker 身份保持；旧进程退出使用 token 比较，不会覆盖接任 PM。绑定与介绍共用项目介绍锁，避免向已交接的终端发送新规则。

项目保存 PM 引导配置状态 `setup`、版本化角色团队 `configuration`，以及兼容的 `pmSkill` 和 `subAgent {backend, model}`。由指定 PM 通过独立 `skill --setup` 入口询问是否开始、维护草案和验证结果；绑定不等于配置完成。完整流程见 [协调指南](coordination-guide.md)。旧项目读取时回退到内置 Skill 与 Pi 默认模型。`skill` 全文读取入口及其目录内资源，不沿用产物预览截断；引用路径不能逃逸 Skill 目录。Worker 在生成 argv 时使用保存的工具和模型，显式 backend 切换不携带其他工具的模型。安装包与能力探测包含这些功能，旧远端运行程序在设置时升级。详见 [PM 设置](onboarding.md)。

`start` 在事务内预留 owner，再调用 `hc run --bg --keep --no-parent --no-notify`。独立 Python wrapper 将项目环境和启动上下文传给现有 Agent 程序，继承原生 PTY，不代理其输入输出。窗口关闭后 core 继续承载程序，SQLite 保留记录。可选的确定性跟进服务运行在项目机器，负责持久通知与检查点，不拥有业务验收权限；服务启停与执行独立。包装程序保留原生进程的 Ctrl+C 处理，避免 Python 的 KeyboardInterrupt 意外终止 Agent。

启动上下文使用有上限的当前摘要，完整记录通过 show/history 读取；历史增长不会被全部塞进一个命令行参数。数据库本身不按摘要上限裁剪。

一个 WorkItem 可以经过多次 Run；每次 Run 有独立 id、归属、token、terminal 和报告。当前项只有一个 activeRunId。Worker 从 Main 的显式 `worker` 调用启动，依赖必须先 accepted / resolved。

## 状态

| 类型 | 状态与合法转换 |
|---|---|
| todo | open → resolved / cancelled；resolved / cancelled 可由 Main 重开为 open |
| promotion | open todo → ready task，沿用 id、sourceRef 和历史 |
| task | ready → running（仅派发）；running ↔ blocked；running / blocked → review；review → accepted / ready；accepted → ready；适当状态可取消 |
| run | starting → running → exited；不确定的启动保留 starting，待人工核对 |
| artifact | 新版本为 review；Main 可明确 accepted / rejected；接受时核对文件哈希 |

ready 或取消之前，旧执行必须已退出并核对。重新派发使用新 Run。任务内部 checklist 不改变整项状态。Worker `submitted=true` 仅把当前任务送入 review。Worker 退出或终端报告 idle / done 都不触发验收。

取消记录有独立默认折叠组，不计入完成数；已完成也默认折叠。所有计数来自可打开的实际记录。

## 写入与证据

`apply` 校验 projectId、Main id、generation、token、state、expected project revision。它在一个数据库事务里提交一项语义操作、修订号和审计记录。相同 requestId / 内容重复提交返回 replayed；同 id 不同内容拒绝。数据库唯一约束和事务防止两个进程同时覆盖。

Worker 的 report 校验 project、run、token 和 activeRunId。旧 Run 的晚到新回报会被拒绝；已成功提交的同一报告可以重试。报告中的多个产物作为整体提交，任意一个无效则全部回滚。

产物登记保留绝对路径、版本、SHA-256、workItemId、runId（如果来自 Worker）、sourceRef 和审阅状态。接受任务必须引用本任务已核验的证据，且文件此刻仍与登记哈希一致。受管产物包另外核验 manifest 列出的全部文件；报告核验、项目采用和内容有效性分别保存。预览随后发生变化的文件会明确显示已变更。这里验证引用和内容完整性；不能自动证明报告语义或测试结论真实。验收也不构成合并、部署授权。

pm.md 保存叙述性目标、决策和关键路径。创建时可显式关联现有 coding-hub pm.md，程序不覆盖它。结构化决策也可存在账本的 decisions 列表，侧栏展示；不会尝试自动双向同步任意 Markdown。

## 独占与恢复

启动锁避免同一项并发派发；wrapper 运行时持有独立进程锁，并让直接子进程继承锁文件描述符。Main 的活跃记录阻止另一次 start。恢复不依赖到期时间，因此暂停或失联不会自动释放 owner。

启动 CLI 遇到超时/响应异常时不删除预留，也不盲目重发。恢复先检查原 core scope、进程锁，再检查携带该 launch label 的存活终端。core 不可用时拒绝恢复。旧终端仍存活（包括 core `--keep` 恢复出的 shell）时也拒绝：先由用户查看原生终端并明确结束，再 reconcile。

这些机制保护通过此接口发起的执行和写入。拥有 shell 的 agent 可以绕过 CLI，任意访问本用户文件或启动别的进程；环境 token、SQLite 和文件锁不是 OS 安全隔离。当前没有跨机器分布式租约或自动故障切换。新角色配置的 Worker 默认独立 worktree；旧配置保留项目 cwd，但跨项目也拒绝同目录多个 live/uncertain 写手。Research 使用独立持久输出目录；只读角色依靠任务契约，不能把它当作 OS 沙箱。Run 保存配置、Skill 哈希、输入产物和工作目录快照。

## 面板与异步

Project 面板和 Files / Changes 共用现有右侧槽位。独立的 projects-tabs 副本增加 Project 切换入口，保留原 Space/Tab 操作及每 Space 的面板状态；没有改写全局 workspace.panels。0.3 使用个人 projects-agents 副本增加右键 Leader 入口和角色标记，原有 Agent 分组、Pin 和导航保留。

只轮询外部账本（可见时每 5 秒），终端/focus/theme 直接使用 Herdr 响应式数据。每次 terminal context 变化推进读取代次；迟到的异步结果不能替换另一个项目。读取失败展示明确错误及上次数据，关闭页面后的回调不会再提交 UI 状态。实际命令用 exec 的 argv 数组，无 shell 字符串拼接。

远端请求使用 Herdr 已有的 `exec(..., {on: machine})` 通道。安装器在项目机器登记其自己的运行 argv；本机路径不跨机器使用。项目账本、文件与执行都在项目机器，客户端只有当前读取结果。scope 与 terminal 保留目标 Core 的本地形式，只有界面导航添加当前机器别名前缀。snapshot/read 带协议版本与来源标识，资料读取拒绝改变后的 Core/账本。详细配置见 [远程说明](remote.md)。

账本浏览仍只读，操作包括展开、搜索、成果成员/版本阅读、刷新及终端导航。较宽的原生成果阅读窗口固定项目来源。首次使用通过轻量表单选择/创建项目并绑定已有终端；用户的绑定动作会自动准备目标机运行程序，并用 `send --if idle` 交代项目规则与配置 Skill 入口。由指定 PM 询问是否开始配置，状态与结果同步展示。不提供聊天输入框或自动派发按钮。支持面板内 1/2/3 切换标签、上下选择、Enter 打开和 Esc 返回；不宣称完整屏幕阅读器支持。

## 后端适配

基础启动以 argv 中的 `{context}` 替换值交代规则，不修改 backend 全局配置。用户可选择 Pi / Claude Code / Codex，或显式传入支持恢复的 argv。重读 `context` 是无 Hook 时的恢复路径。没有自动安装 SessionStart、PreToolUse、Stop 或 compaction Hooks；没有 Hook 完成闸门。

运行程序依赖 POSIX `fcntl`，适用于 Linux/macOS，实际验证目标为 Linux。0.2 支持 Herdr 机器连接上的远端项目，Main/Workers 仍在同一项目机器。Windows 运行程序和跨主机 Worker 调度尚未实现。
