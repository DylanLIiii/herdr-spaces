# Project 原生 UI 设计

借鉴 BoardUI 的公开组件文档，以 GPUI 原生视图实现；沿用 Herdr 语义主题和既有账本协议。

## 参考与适配

- [Project Board](https://www.boardui.com/zh-hans/components/project-board)：阶段分组、卡片层级、详情渐进展开。396px 侧栏使用纵向分组，不放五列看板。
- [Task List](https://www.boardui.com/zh-hans/components/task-list)：可折叠完成记录、资源与任务关联。状态由账本提供，不使用演示计时器。
- [Agent Progress](https://www.boardui.com/zh-hans/components/agent-progress)：阶段与步骤可扫描；仅展示真实 checklist 已完成数量。
- [Agent Creator](https://www.boardui.com/zh-hans/components/agent-creator)：配置按用途分组，当前设置与编辑状态分离。无需头像定制、语音或聊天功能。

## 信息结构

侧栏顶部保留 Project 标题、刷新、关闭；项目摘要展示项目名、简短目标、PM 实时状态与进入 PM 操作。三个紧凑数量块分别表示待安排（open/ready）、执行中（running）和已完成（accepted/resolved）。待处理入口仅聚合 blocked/review，并明确细分数量；点击筛选，不推断是否必须由人处理。

任务按受阻、待核验、进行中、待执行、待办、已完成、已取消分组。已完成和已取消默认折叠。卡片显示标题、文本状态、下一步或阻塞说明；关联执行终端与真实 checklist 数量作为次级信息。任务详情优先呈现下一步、验收条件和执行回报，技术标识放在末尾。

会话区保留 PM 与 Worker 分组，每行区分角色、终端、关联任务与执行状态。空闲或退出不代表任务通过验收。资料区以可读名称、版本和采纳状态展示证据，完整目标可在这里阅读。

首次绑定展示项目→Skill→SubAgent 引导。现有项目默认展示可编辑摘要，点击对应分组再编辑；项目切换独立展开。交接始终进入独立确认页。成功、待发送、发送结果不确定分别反馈，不以“保存成功”暗示 Agent 已接收。

## 视觉规范

- 间距以 4px 为基础：行内 6–8，组件内 10–12，主要区块 16。
- 标题 15–17px；正文 12–13px；辅助信息 11px；数量强调 18px。
- 使用 background / surface / raised 区分层级；border 用于结构边界，避免每行叠加边框。
- 状态用颜色与文字共同表达；blocked 用于等待处理，working 用于真实执行，done 用于账本已验收。
- 主操作使用 solid / solid_foreground，普通导航使用轻背景，配置和刷新降低视觉权重。
- 长标题和路径在列表截断并提供 tooltip，详情保留全文。正文滚动，设置窗口底部操作固定；详情模式压缩顶部摘要。
- 支持现有键盘任务导航、Tab/Shift-Tab 表单导航、Escape 返回/关闭；不新增全局快捷键。

## 环境边界

只更新已安装 projects-pm-panel、projects-pm-setup、projects-pm-agents 及必要运行资源，保留 sulan-tools 布局和所有其他组件。安装前备份，验证前记录窗口状态，结束恢复。测试数据只存在隔离账本或明确标记的视觉 fixture 中。
