# 验证记录

## 0.4.0 PM 协调与研究闭环

- `npm run check`、`npm test`（**97 Python + 32 JavaScript**）、`git diff --check` 通过。覆盖旧 schema 事务迁移、回报幂等/回滚、检查点去重、消息不明与 PM 交接、配置暂缓/恢复、角色路由、真实 Git worktree 隔离、输入证据变更拒绝、产物发布中断及版本关联。
- **27 项真实 Core 与 Linux/Xvfb 原生检查通过**，见 [result.json](coordination/result.json)。使用官方 SHA-256 校验通过的 Herdr App 0.1.15、现有 Core 0.1.19、隔离 socket/账本/app home 和确定性 PM/Research 程序；没有模型调用。验证服务停止期间回报保留、重启通知、服务崩溃恢复、PM 交接、旧身份失效、研究核验/采用/后续任务，以及清理执行目录后已发布报告仍可读取。
- 已直接查看真实截图：[项目](coordination/project.png)、[研究阅读](coordination/reader.png)、[320px 长内容](coordination/long-narrow.png)、[离线阅读](coordination/offline-narrow.png)、[420×600 首次绑定](coordination/setup-first-narrow.png)、[交接](coordination/setup-handoff-narrow.png)、[暗色错误状态](coordination/setup-error-dark.png)、[浅色配置](coordination/setup-light.png)。窄布局正文可滚动，底部操作固定；错误提示与重试保留在可见区域；长来源链接改为可读标签。首次配置清楚提示由 PM 询问是否开始。
- **8 项真实远端 machine --via 协议检查通过**，见 [remote-result.json](coordination/remote-result.json)：双客户端共享一份远端成果、哈希与成员读取、错误来源拒绝、断线无本地回退、重连身份保持、正文检索。环境为同机隔离 Core，未宣称物理主机 SSH 端到端验证。
- 两个主要生产 mod 及安装副本通过 `herdr-app check`，机械设计检测返回空列表。JS 回归覆盖键盘导航、输入焦点、问题分流、成果版本与成员切换、迟到异步响应及配置入口；这不等同完整屏幕阅读器审计。
- macOS 真实 Core 闭环曾通过，但后续隔离窗口返回重复旧 GPU 帧；加入截图不同场景校验后拒绝使用这些画面作为视觉证据。最终发布的本轮截图全部来自 Linux/Xvfb。没有鼠标/键盘自动化操作用户的日常显示器；测试结束关闭自己创建的 Core、窗口、服务和显示。
- Feynman/OpenCode 命令按本机实际 help 核对，真实模型/检索/实验未调用；fixture 只验证契约和交付链路。能力未实测时配置保持待验证。服务不自动配置开机自启，机器重启后通过 `service start` 或既有进程管理器恢复。
- 完整要求映射与边界见 [implementation-coverage.md](implementation-coverage.md)，使用与迁移见 [coordination-guide.md](coordination-guide.md)。下方 0.3.x 记录为历史基线，不作为本轮新增证据。

0.3.1 修复与下列 0.3.0 基线均在 Linux、Python 3.12、Node 24、Herdr App 0.1.14 与 hc 0.1.19 上验证。所有原生运行使用独立 app home、SQLite 目录、core session/socket 和 Xvfb 显示。测试结束后关闭了这些测试进程；用户当前的终端、core、布局、settings 与后端 Hooks 未改动。

## BoardUI 参考的原生 UI/UX 改造（未发布）

- 最终 `npm test` **85 项测试通过（56 Python + 29 JavaScript）**；三个已安装模块 `projects-pm-panel`、`projects-pm-setup`、`projects-pm-agents` 全部通过 `herdr-app check`，`git diff --check` 通过。

- 当前使用原有 **sulan-tools** 布局。仅更新其引用的 `projects-pm-panel`、`projects-pm-setup`、`projects-pm-agents`；本轮没有改写布局文件，更新前后 SHA-256 相同。Sulan、原标签栏与其他工具保留。下方 `projects-pm` 布局体验属于此前历史阶段。
- 设计映射见 [native-ui-design.md](native-ui-design.md)：原生摘要数量、待处理筛选、任务分组、详情、角色标签，以及已有项目的配置摘要与按需编辑。没有引入 React、WebView 或 BoardUI Pro 源码。
- 实际 macOS 原生窗口中检查了[项目摘要与任务](native-ui/project.png)、[会话](native-ui/sessions.png)、[长标题详情](native-ui/detail.png)、[设置摘要](native-ui/settings.png)、[交接确认](native-ui/handoff.png)和 [300×640 窄窗口](native-ui/narrow.png)。截图使用隔离测试账本，图片仅裁剪，没有重绘。
- 使用生产 View 的临时命令驱动器、隔离账本与确定性 Core 终端，实际完成首次绑定、保存 Codex / `fixture-model`、取消交接和确认交接；保存配置保持 generation 1，交接后 generation 2。两端均完整读取 Skill（1743 字符）和 SubAgent 引用（1564 字符）。未调用真实模型，也未在用户显示器进行鼠标/键盘自动化。
- 错误恢复同时通过 View 回归和真实隔离流程验证。实际运行的 [故障注入入口](native-ui/recovery-fault-wrapper.py) 在首次 `introduce` 交付前退出 73，其他命令调用真实 runtime。窗口保持已绑定状态；重试新增命令只有 `introduce`，Main id 和 generation 1 不变，真实 Core 测试终端随后返回 Skill 全文读取回执。首次绑定与已有项目保存后的恢复均验证，完整前后状态、命令序列与接收回执见 [recovery-result.json](native-ui/recovery-result.json)。
- 最终 480×560 配置窗口的[设置页](native-ui/settings-small.png)、[交接页](native-ui/handoff-small.png)、[发送错误页](native-ui/recovery-error-small.png)均已原生截图并直接查看。验证发现错误提示可能藏在长摘要下方，已将错误与重试按钮移至固定可见区域，并固定底部动作；更新安装副本后重新通过 13 项设置窗口测试，随后完整 85 项测试、已安装 setup 原生检查及 `git diff --check` 再次通过（后台任务 `b3e1822e7`）。正文可滚动，保存、取消和交接确认保持可见。
- View 回归还验证自定义 Skill 无效时返回编辑区、外部 Core 不允许交接、筛选和键盘导航使用同一任务集合、已取消不计入完成，以及终端状态不会推断任务验收。
- 本机安装前备份三份模块和原布局；备份路径、配置传播、布局哈希与清理结果见 [native-ui/result.json](native-ui/result.json)。两个测试终端和临时驱动器均已移除，验证前后用户的 space/tab/pane/agent 焦点一致，宿主无错误且无遗留 overlay。
- [实际安装后的 Project 面板](native-ui/installed.png)也已直接查看；显示用户真实项目的已有记录，未写入测试任务。

## PM 重新绑定、Skill 与 SubAgent 配置（未发布）

初次实现在 macOS 工作区验证，随后按用户要求安装到本机 `projects-pm` 个人布局，并在真实 Herdr 窗口中体验与优化。原布局保留，项目账本沿用既有路径。

- `npm test`：**80 项测试通过（56 Python + 24 JavaScript）**。覆盖重新绑定的代次检查、旧凭据失效、记录保留、旧 Managed PM 退出不覆盖接任 PM、已有 Worker 继续报告，以及界面的显式确认。
- Skill 测试读取完整入口及超过预览上限的引用文件，验证自定义目录、资源列表和越界路径拒绝；安装与自动准备测试确认内置 Skill 及引用文件随包部署。
- SubAgent 测试验证保存的 Coding 工具和模型进入启动 argv、单次覆盖、切换工具不沿用不兼容模型、自定义 argv 和程序缺失的错误处理。未调用真实模型服务。
- `herdr-app check mods/project-setup` 与 `herdr-app check mods/project` 通过，`git diff --check` 通过。
- 修正两项旧测试对 macOS 临时目录 `/var` / `/private/var` 的路径假设，并隔离新 CLI 测试中的宿主终端身份。
- 初次实现阶段缺少 Xvfb，未运行 Linux 窗口 smoke；后续本机体验使用 Herdr App 0.1.14 / Core 0.1.19 的 macOS 原生窗口与截图接口，不依赖 Xvfb。

### 本机安装与 UI/UX 体验

- 安装到 `~/.config/herdr-app/projects-runtime/projects-pm`，布局为 `projects-pm`，CLI 为 `~/.local/bin/projects-pm-project`。既有账本路径与远端登记名保持，旧布局可随时切回。
- 四个已安装原生模块 `projects-pm-agents`、`projects-pm-tabs`、`projects-pm-panel`、`projects-pm-setup` 全部通过 `herdr-app check`。
- 使用独立临时账本、两个本机 Core 测试终端以及临时 View 驱动器。驱动器调用生产设置窗口的方法，实际执行绑定、受控介绍、Skill 全文读取、保存 SubAgent 配置和两次 PM 交接；没有对真实显示器做鼠标/键盘自动化，也没有让模型执行任务。
- 接任 PM 实际读取 Skill 正文和 `references/subagents.md`，代次为 1 → 2 → 3；保存的 Codex / `ux-fixture-model` 随介绍到达测试终端。此模型名仅作配置传递验证，未连接模型服务。
- 直接查看了[配置表单](pm-ux/configure.png)、[交接确认](pm-ux/handoff.png)、[保存结果](pm-ux/success.png)，并检查 480×560 逻辑像素对话框下正文滚动区域与固定底部操作的布局。图片仅裁剪原生窗口中的对话框，没有重绘界面。
- 修正介绍失败后重试误走绑定入口的问题；对自定义 Skill 空路径、已退出但属于其他 Core 的 PM 增加界面保护。最终确认页调整后，11 项设置窗口测试再次通过。
- 已从实际项目侧栏的命令入口打开安装后的 PM 设置，核对真实项目显示且 `status.errors` 为空；随后关闭对话框。测试终端和临时 UI 驱动器已清理，当前保留 `projects-pm` 布局与用户原来的终端焦点。
- 结构化体验结果见 [pm-ux/result.json](pm-ux/result.json)。下方 Linux 原生截图与集成结果属于历史版本，不混作本轮验证证据。

## 0.3.1 修复验证

- **61 项自动化测试通过**（43 Python + 18 JavaScript），包含全部原有测试。
- 新 CLI 回归在独立 HOME 中安装 Core，将后台 PATH 指向空目录，先复现 `No such file or directory: 'hc'`，修复后通过真实 `setup` 命令读取正确 Core 与终端。
- 新测试覆盖官方 `herdr-core` 安装但没有 `hc` 别名、自定义安装目录、含空格的显式路径、PATH 上同名但非 Herdr 的程序、无效显式 override 不回退，以及程序缺失时的准确提示。
- 旧运行程序能力测试先复现 0.3.0 被错误复用，修复后自动准备新运行程序并保留自定义账本目录。界面测试确认先完成升级，再调用 setup。
- 安装测试验证新桌面布局通过 `--remote-name` 同时为 Project 和 Agents 保留原远端登记名。
- **18 项受限 PATH 原生升级检查通过**，见 [core-path/result.json](core-path/result.json)。目标环境 PATH 为 `/usr/bin:/bin`，只有独立 HOME 下的 `~/.local/bin/herdr-core`，没有 `hc` 别名；真实 machine exec 也确认无法从 PATH 找到两者。使用仓库 0.3.0 提交 `35e78579319bfed98157308b91ff76cbed6744cb` 的源码快照先复现原错误，再通过原生 Leader 窗口自动升级、保留含空格的自定义账本路径，完成现有终端绑定、一次可见介绍和任务写入。未重启目标 Core，也未重新启动 Agent。
- [最终窗口截图](core-path/leader.png) 已直接查看，账本显示来自原生 Leader 的新任务。测试使用同机隔离 Core 的真实 `--via` 通道和确定性 Agent，没有连接用户的 gpu-dev。
- 本轮测试 Agent 最初限定解释器路径必须等于自身 Python，导致运行程序选用 `/usr/bin/python3` 后测试不响应；确认绑定/发送已成功，再把测试改为校验目标机器登记的完整命令，重跑通过。
- 0.3.1 安装归档已独立解压，验证自定义桌面安装名保留旧远端登记、运行版本/能力及四个安装 mod 原生检查。下方保留 0.3.0 的一般原生回归证据，本轮未把它们重复计作新增检查。

## 0.3.0 基线结果

- **36 项 Python 测试通过**：持久 Main 身份、todo 同 id 提升、过期身份、跨项目/角色隔离、乐观版本冲突、并发写入、幂等回报、晚到报告、原子回滚、证据哈希、步骤与整项验收区别、依赖环、终端/core scope 绑定、启动中断保留预留、进程锁、恢复代次、已有 pm.md 保留、长历史的有界启动摘要、安装冲突/路径空格/个人 mod 重命名，以及真实子进程 Ctrl+C 行为。新增 runtime-only / 登记冲突、Core 身份与不可用处理、资料来源校验和旧绑定歧义测试。0.3 增加现有终端绑定、单 Leader 排他、终端身份解析、受控介绍与去重、attached 恢复、自动准备及保留自定义账本的升级测试。一个测试可包含多个上述断言。
- **17 项 JavaScript 测试通过**：账本分组、真实 View 渲染与终端导航、键盘选择、跨项目异步响应丢弃、断连时标明旧记录、关闭时抑制迟到结果，以及远端同名终端、跨机 peek、迟到资料、协议兼容性、来源变更和自定义 argv。0.3 增加缺少运行程序的可操作空状态、设置流程自动准备、关闭时阻止后续绑定、已有 Leader 导航，以及两个隔离 mod 的共享代码一致性。
- **18 项真实 Herdr/core 集成检查通过**，结果见 [native/result.json](native/result.json)。使用确定性测试进程，实际创建 Main/Worker 原生终端，写入账本、报告与证据，验证 idle/退出不代表验收、重复 start 不会开第二个 owner、运行中不能恢复为另一个 Main、Main 验收才完成任务、重启保留 Main id 并提升 generation。
- **16 项远程机器通道与原生集成检查通过**，结果见 [remote/result.json](remote/result.json)。在三个隔离 Core 中，通过真实 `hc machine --via` / `hc exec --on` 验证目标机 runtime 发现、本地与远端同名项目/终端隔离、两个不同机器别名的客户端共用一个 Main、防止重复启动、远端证据读取、真实窗口导航、断开字节流连接后 Main 保持存活，以及重连后的身份/代次保持。
- **13 项 Leader 引导原生检查通过**，结果见 [onboarding/result.json](onboarding/result.json)。从未安装运行程序的远端现有 Agent 开始，验证左侧右键入口、自动准备、原生表单、复用当前终端、一次可见介绍、终端身份写入任务、Leader 标记，以及关闭和窄窗口布局。测试 Agent 为确定性程序，明确标示 synthetic / no model。
- 原生键盘输入实际打开详情、切换标签、进入 Worker，再返回本项目 Main；关闭面板后 Main 仍存活。
- 原侧栏/标签源码及安装副本通过 `herdr-app check`，新版本的侧栏、标签、Agents、Leader 设置四个安装 mod 也均通过检查。实际窗口的 Tasks / Sessions / Artifacts、详情和窄窗口状态无 host errors；窗口没有欢迎浮层遮挡。
- Python 编译检查与全部运行 JavaScript 的 `node --check` 通过。
- 原始 Herdr App checkout 保持无修改。
- 交付归档已解压到新的临时目录，再从该副本以自定义名称安装；CLI probe、四个安装后的 mod 原生 check、随包远端自动准备及幂等重试均通过。此前项目创建/列出也已验证。包中不包含 SQLite 数据、运行日志或缓存。

## 原生截图

这些文件均由 `herdr-app shot` 从真实 GPUI 窗口捕获，不是 HTML 原型。终端和项目数据明确标为合成测试场景，没有调用模型或假装真实任务完成。

| 文件 | 内容 |
|---|---|
| [tasks.png](native/tasks.png) | 1600×1000，Graphite 暗色，待办与待核验分组 |
| [sessions.png](native/sessions.png) | 本项目唯一 Main 与 Worker、真实运行状态 |
| [files.png](native/files.png) | 目标、pm.md 与登记产物 |
| [task-detail.png](native/task-detail.png) | 范围、标准、步骤、来源、执行回报与终端入口 |
| [artifact.png](native/artifact.png) | 原生 Markdown 预览、版本、路径、来源任务 |
| [tasks-light.png](native/tasks-light.png) | Paper 浅色 |
| [narrow.png](native/narrow.png) | 1024×800 窗口，现有终端与侧栏布局 |
| [narrow-detail-scrolled.png](native/narrow-detail-scrolled.png) | 详情独立滚动，头部/页脚固定，下方终端入口可到达 |
| [terminal-only.png](native/terminal-only.png) | 面板关闭后原生终端收回宽度 |

远程验证截图同样来自真实 GPUI 窗口，已逐张查看：

| 文件 | 内容 |
|---|---|
| [remote/tasks.png](remote/tasks.png) | 服务器项目账本，机器归属显示为 fixture |
| [remote/artifact.png](remote/artifact.png) | 在目标机读取的证据文件与 Markdown 预览 |
| [remote/local.png](remote/local.png) | 切回本机的同名项目/终端后，显示独立的本机记录 |
| [remote/reconnected.png](remote/reconnected.png) | 断线重连后继续显示原服务器项目 |

Leader 引导的最终截图也已直接查看：[左侧右键入口](onboarding/menu.png)、[创建/选择项目窗口](onboarding/form.png)、[绑定后的原生终端与账本](onboarding/leader.png)、[1024×800 窄窗口](onboarding/narrow.png)。缺少 runtime 的初始状态见 [empty.png](onboarding/empty.png)。

本机暗色账本和较矮窗口详情滚动截图也已查看。没有用机械 UI 检测器代替原生检查。

## 修复过的问题

- 验证脚本的 `scripts` 命名空间与环境中同名包冲突，增加明确包入口。
- Python wrapper 默认 KeyboardInterrupt 会终止本来能够自行处理 Ctrl+C 的 native 程序。添加父进程信号处理，直接子进程仍获得原生信号；测试先复现失败再通过。
- 键盘处理方法与实例上的 context key 同名，重命名为 handleKey，并补回归验证。
- 测试初次启动时欢迎窗口覆盖界面。修正只属于隔离环境的首次启动状态；不以“无代码错误”代替无遮挡截图。
- Herdr 的 `app.theme` 选择配色方案，不改变系统明暗模式。测试明确切换隔离 settings 的 appearance 后再检查两种外观。
- 远程验证脚本先遇到命令参数重名，随后截图发现切换 Space 的面板恢复会覆盖过早的打开操作。修正脚本顺序后，原生导航和完整远程检查通过。
- Leader 流程中，测试 Agent 已写入任务但发送确认尚未落账，修正了测试的等待条件；原生截图还发现设置 mod 缺少 `place: none` 导致意外停靠，补上声明和防回归检查后重新验证通过。
- GPUI 的每个 mod 有独立模块根目录，设置 mod 不能从相邻 mod 导入 transport。安装器为两个 mod 提供同源副本，自动化测试检查其一致性。

## 实际边界

- 未启动付费 LLM，也未验证某个模型是否持续遵守维护规则。默认 Pi/Claude/Codex argv 和自定义 `{context}` 启动方式已实现；目标 backend 版本、登录环境及实际会话恢复参数仍应在目标机器确认。
- 本版实际验证在 Linux。POSIX 进程锁适用于 Linux/macOS，但 macOS 原生窗口未测试；Windows 运行程序尚未实现。远程测试使用同机的隔离 Core 和正式 machine transport，未访问真实 SSH 服务器。
- Worker 使用项目 cwd，没有自动创建独立 worktree；没有 Coding Hub 全量通道路由、后台长期调度、自动订阅或远程故障切换。
- 安装包已在隔离目录安装验证；没有替用户切换日常桌面布局或安装 backend Hooks。
- 自动化及原生集成检查针对上述明确路径，不等于完整可访问性审计、所有异常的穷尽证明或外部独立评审。
