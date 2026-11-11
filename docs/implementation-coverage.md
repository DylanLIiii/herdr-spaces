# 0.4.0 方案覆盖与验收

实现范围对应 [设计方案](pm-coordination-and-research.md) 的 A–D 阶段，含用户明确指定的「PM 激活 Skill 并询问是否开始配置」。本文件说明实现与证据映射；实际使用见 [协调指南](coordination-guide.md)。

| 要求 | 实现位置 | 验证 |
| --- | --- | --- |
| 兼容旧账本、稳定 PM 身份、幂等与版本冲突 | `schema.py`、`store.py`、`onboarding.py` | schema 1→2 保留记录；旧 PM 拒绝；旧协议与晚到报告回归 |
| PM 同时规划与协调 | 内置 PM Skill、`runtime.context`、结构化项目/任务字段 | context/Skill 读取及真实 PM fixture 的核验、决策、后续任务 |
| 回报、收件箱、检查点与后台跟进 | `coordination.py`、`store.report`、CLI `service/inbox` | 14 项协调测试；真实 Core 停止/重启、崩溃、交接、未确认发送 |
| 指定 PM 激活配置 Skill、询问是否开始 | `skills/herdr-spaces-setup/SKILL.md`、`setup_flow.py`、`onboarding.introduction` | 配置同意、暂缓、草案版本、恢复、交接；独立入口兼容自定义 PM Skill |
| UI 只做轻量绑定、展示配置结果 | `mods/project-setup/` | 不再先填写模型；UI 不改变团队事实；显示未验证能力和继续配置入口 |
| 团队模板、角色/难度/后端分离 | `teams.py`、`manager.py` | development/research/mixed；direct/Coding Hub；Pi/Claude/Codex 兼容，OpenCode/Feynman argv |
| 按真实能力检查配置 | `capabilities`、`setup.check/finish` | 安装≠认证≠模型≠检索；fixture 不能把项目标为 ready；配置检查绑定 revision |
| 执行快照与并行隔离 | `workspaces.py`、`runtime.start/execute` | 7 项真实 Git worktree 测试；只读/Research 目录分离；启动不明保留现场 |
| 持久产物、版本与完整性 | `artifacts.py`、`store.add_artifact` | 11 项产物测试；复制中断、事务回滚重试、清理执行目录、变更检测、路径边界 |
| Research 过程与证据契约 | Feynman 适配、bundle role 清单、claims、researchContract | Deepresearch/Autoresearch 文件角色校验；benchmark 与迭代契约；真实 Core fixture 交付研究包 |
| 核验、采纳、有效性分开 | artifact.review/disposition/validity | 已核验的负面结论可不采用；采用需当前、已核验且内容完整 |
| 决策、后续任务与复用 | artifact.followup、decision.artifactRefs、inputArtifactRefs、search | 版本锁定、待办去重、无自动派发、正文/元数据检索、输入完整性检查 |
| 原生任务/会话/成果体验 | `mods/project/` | 32 项 JS 回归中的 19 项面板测试；真实 mod 加载；原生截图按下述记录 |
| 远端同源读取与恢复 | transport、read 来源校验、runtime registry | [8 项真实 machine 通道检查](coordination/remote-result.json)，两个客户端、断线重连、哈希与身份保持 |
| 安装、升级和打包 | install.py、bootstrap.py、package.py、能力探测 | 临时目录安装、远端包准备与旧登记路径保留、归档解压验证 |

自动化基线：`npm run check`、`npm test`（97 Python + 32 JavaScript）、`git diff --check` 均通过。机械设计检测返回空问题列表；它不替代实际原生画面检查。

原生生命周期脚本：`scripts/workflow_smoke.py`。确定性 PM/研究程序通过真实 Herdr Core 执行配置、服务中断、回报、通知、交接、核验、采纳与后续任务，随后删除研究执行目录并读取已发布成果。27 项检查通过，平台为 Linux/Xvfb；结果、平台与截图见 `docs/coordination/result.json` 和同目录文件。

远端协议脚本：`scripts/remote_protocol_smoke.py`。测试使用同机隔离 Core 的真实 machine --via 通道；未把它当作物理服务器 SSH 的验证。

## 明确的实现边界

- 真实模型、付费研究检索和 Autoresearch 实验未启动。已验证适配 argv、任务契约及 fixture 闭环，不能据此宣称模型研究质量或某个账户服务可用。产品配置中保留 unverified 状态。
- Skill 引导由 PM 执行，CLI 校验身份、结构、版本和状态；它不能证明模型确实遵守用户意图或自由文本证据为真。
- 当前并行隔离保护受管写任务；只读角色和拥有同用户 shell 的程序不是 OS 沙箱。原始 PTY 发送保留 uncertain，不承诺 exactly-once。
- 跟进服务独立于窗口，但机器重启后需 `service start`，或用已有进程管理器运行 `service run`；不自动修改系统服务配置。
- 大型媒体与数据使用有界外部清单，阅读器主要支持 Markdown/文本与分段读取，不内嵌 PDF 编辑器。研究过程的文件角色与字段校验不代替语义核验。
- 可用性覆盖了指定场景与键盘逻辑，不等同完整屏幕阅读器审计。
- 跨机器 Worker、GitHub/飞书接单、语义索引与更丰富的里程碑视图按确认范围延后。

## 验证过程中的修正

远端包最初漏列新增模块，补齐文件清单后回归通过。真实 Core 启动时 status 可为 null；通知被收到与送达回执入账存在时差；CLI 的 requiredChecks 是派生字段。测试分别修正了这些边界。

macOS 隔离窗口在部分运行中持续返回旧 GPU 帧，空 host errors 无法证明页面已经渲染；已加入截图多样性检查，这些旧帧不作为视觉通过证据。最终视觉验证改用 Linux/Xvfb 的独立窗口与显示，保留真实 Core 测试、未调用模型的边界。
