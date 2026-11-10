# 验证记录

实现版本 0.2.0，在 Linux、Python 3.12、Node 24、Herdr App 0.1.14 与 hc 0.1.19 上验证。所有原生运行使用独立 app home、SQLite 目录、core session/socket 和 Xvfb 显示。测试结束后关闭了这些测试进程；用户当前的终端、core、布局、settings 与后端 Hooks 未改动。

## 结果

- **26 项 Python 测试通过**：持久 Main 身份、todo 同 id 提升、过期身份、跨项目/角色隔离、乐观版本冲突、并发写入、幂等回报、晚到报告、原子回滚、证据哈希、步骤与整项验收区别、依赖环、终端/core scope 绑定、启动中断保留预留、进程锁、恢复代次、已有 pm.md 保留、长历史的有界启动摘要、安装冲突/路径空格/个人 mod 重命名，以及真实子进程 Ctrl+C 行为。新增 runtime-only / 登记冲突、Core 身份与不可用处理、资料来源校验和旧绑定歧义测试。一个测试可包含多个上述断言。
- **12 项 JavaScript 测试通过**：账本分组、真实 View 渲染与终端导航、键盘选择、跨项目异步响应丢弃、断连时标明旧记录、关闭时抑制迟到结果，以及远端同名终端、跨机 peek、迟到资料、协议兼容性、来源变更和自定义 argv。
- **18 项真实 Herdr/core 集成检查通过**，结果见 [native/result.json](native/result.json)。使用确定性测试进程，实际创建 Main/Worker 原生终端，写入账本、报告与证据，验证 idle/退出不代表验收、重复 start 不会开第二个 owner、运行中不能恢复为另一个 Main、Main 验收才完成任务、重启保留 Main id 并提升 generation。
- **16 项远程机器通道与原生集成检查通过**，结果见 [remote/result.json](remote/result.json)。在三个隔离 Core 中，通过真实 `hc machine --via` / `hc exec --on` 验证目标机 runtime 发现、本地与远端同名项目/终端隔离、两个不同机器别名的客户端共用一个 Main、防止重复启动、远端证据读取、真实窗口导航、断开字节流连接后 Main 保持存活，以及重连后的身份/代次保持。
- 原生键盘输入实际打开详情、切换标签、进入 Worker，再返回本项目 Main；关闭面板后 Main 仍存活。
- 源码与安装后的两个 mod 均通过 `herdr-app check`。实际窗口的 Tasks / Sessions / Artifacts、详情和窄窗口状态无 host errors；窗口没有欢迎浮层遮挡。
- Python 编译检查与全部运行 JavaScript 的 `node --check` 通过。
- 原始 Herdr App checkout 保持无修改。
- 交付归档已解压到新的临时目录，再从该副本运行安装器；重定位后的 CLI 创建/列出项目成功，两个安装后的 mod 再次通过原生 check。包中不包含 SQLite 数据、运行日志或缓存。

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

本轮也直接查看了本机暗色账本和较矮窗口详情滚动截图。没有用机械 UI 检测器代替原生检查。

## 修复过的问题

- 验证脚本的 `scripts` 命名空间与环境中同名包冲突，增加明确包入口。
- Python wrapper 默认 KeyboardInterrupt 会终止本来能够自行处理 Ctrl+C 的 native 程序。添加父进程信号处理，直接子进程仍获得原生信号；测试先复现失败再通过。
- 键盘处理方法与实例上的 context key 同名，重命名为 handleKey，并补回归验证。
- 测试初次启动时欢迎窗口覆盖界面。修正只属于隔离环境的首次启动状态；不以“无代码错误”代替无遮挡截图。
- Herdr 的 `app.theme` 选择配色方案，不改变系统明暗模式。测试明确切换隔离 settings 的 appearance 后再检查两种外观。
- 远程验证脚本先遇到命令参数重名，随后截图发现切换 Space 的面板恢复会覆盖过早的打开操作。修正脚本顺序后，原生导航和完整远程检查通过。

## 实际边界

- 未启动付费 LLM，也未验证某个模型是否持续遵守维护规则。默认 Pi/Claude/Codex argv 和自定义 `{context}` 启动方式已实现；目标 backend 版本、登录环境及实际会话恢复参数仍应在目标机器确认。
- 本版实际验证在 Linux。POSIX 进程锁适用于 Linux/macOS，但 macOS 原生窗口未测试；Windows 运行程序尚未实现。远程测试使用同机的隔离 Core 和正式 machine transport，未访问真实 SSH 服务器。
- Worker 使用项目 cwd，没有自动创建独立 worktree；没有 Coding Hub 全量通道路由、后台长期调度、自动订阅或远程故障切换。
- 安装包已在隔离目录安装验证；没有替用户切换日常桌面布局或安装 backend Hooks。
- 38 项自动化测试、18 项本机与 16 项远程原生集成检查针对上述明确路径，不等于完整可访问性审计、所有异常的穷尽证明或外部独立评审。
