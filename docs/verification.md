# 验证记录

实现版本 0.1.0，在 Linux、Python 3.12、Node 24、Herdr App 0.1.14 与 hc 0.1.19 上验证。所有原生运行使用独立 app home、SQLite 目录、core session/socket 和 Xvfb 显示。测试结束后关闭了这些测试进程；用户当前的终端、core、布局、settings 与后端 Hooks 未改动。

## 结果

- **20 项 Python 测试通过**：持久 Main 身份、todo 同 id 提升、过期身份、跨项目/角色隔离、乐观版本冲突、并发写入、幂等回报、晚到报告、原子回滚、证据哈希、步骤与整项验收区别、依赖环、终端/core scope 绑定、启动中断保留预留、进程锁、恢复代次、已有 pm.md 保留、长历史的有界启动摘要、安装冲突/路径空格/个人 mod 重命名，以及真实子进程 Ctrl+C 行为。一个测试可包含多个上述断言。
- **6 项 JavaScript 测试通过**：账本分组、真实 View 渲染与终端导航、键盘选择、跨项目异步响应丢弃、断连时标明旧记录、关闭时抑制迟到结果。
- **18 项真实 Herdr/core 集成检查通过**，结果见 [native/result.json](native/result.json)。使用确定性测试进程，实际创建 Main/Worker 原生终端，写入账本、报告与证据，验证 idle/退出不代表验收、重复 start 不会开第二个 owner、运行中不能恢复为另一个 Main、Main 验收才完成任务、重启保留 Main id 并提升 generation。
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

本轮直接查看了暗色账本、资料详情、较矮窗口详情滚动截图；之前已查看浅色任务/会话与布局。没有用机械 UI 检测器代替原生检查。

## 修复过的问题

- 验证脚本的 `scripts` 命名空间与环境中同名包冲突，增加明确包入口。
- Python wrapper 默认 KeyboardInterrupt 会终止本来能够自行处理 Ctrl+C 的 native 程序。添加父进程信号处理，直接子进程仍获得原生信号；测试先复现失败再通过。
- 键盘处理方法与实例上的 context key 同名，重命名为 handleKey，并补回归验证。
- 测试初次启动时欢迎窗口覆盖界面。修正只属于隔离环境的首次启动状态；不以“无代码错误”代替无遮挡截图。
- Herdr 的 `app.theme` 选择配色方案，不改变系统明暗模式。测试明确切换隔离 settings 的 appearance 后再检查两种外观。

## 实际边界

- 未启动付费 LLM，也未验证某个模型是否持续遵守维护规则。默认 Pi/Claude/Codex argv 和自定义 `{context}` 启动方式已实现；目标 backend 版本、登录环境及实际会话恢复参数仍应在目标机器确认。
- 本版实际验证在 Linux。POSIX 进程锁适用于 Linux/macOS，但 macOS 原生窗口未测试；Windows 与远程账本未实现。
- Worker 使用项目 cwd，没有自动创建独立 worktree；没有 Coding Hub 全量通道路由、后台长期调度、自动订阅或远程故障切换。
- 安装包已在隔离目录安装验证；没有替用户切换日常桌面布局或安装 backend Hooks。
- 26 项自动化测试和 18 项集成检查针对上述明确路径，不等于完整可访问性审计、所有异常的穷尽证明或外部独立评审。
