# SubAgent 分工、配置与交付

首次配置和配置恢复使用 `skill --setup`；由指定 PM 询问是否开始，再按实际同意推进。团队配置位于 `show.configuration`，旧项目的 `subAgent {backend, model}` 仅作兼容默认。常规配置通过 `setup.draft` / `setup.confirm` 保存，不通过重新绑定 PM 修改。

## 按角色派发

运行 `team-template` 查看当前模板、`capabilities` 查看工具安装情况、`operations` 查看完整写入字段。工具安装不证明账户或模型可用，能力未验证时如实说明。

| 角色 | 工作范围 | 默认难度 |
| --- | --- | --- |
| worker | 在约定范围实现并验证 | craft |
| explore | 只读定位本地代码 | breeze |
| librarian | 官方文档、API、单仓库来源查询 | craft |
| reviewer | 独立核验，不改实现 | craft / sage |
| research | Feynman 多来源研究或有限实验 | 使用自身工作流 |
| oracle | 只读困难决策分析 | apex |

PM 维护目标、优先级、依赖和验收，也负责角色选择、派工、解阻塞及交接。子代理仅执行自己的范围；可与同项目 Worker/Reviewer 通过 `hc send` 直接核对事实和局部返工。等待用 `hc wait`，关键依据用 `post --file JSON --notify` 挂到自己任务，recipients 使用明确 Run id 或 pm。回复可带 replyTo、引用可带 artifactRefs。不广播，不把同级消息当成扩大范围或递归派工授权。一个任务由一个 Run 承担；已有执行不明时先核对，不重复启动。

## 工具与隔离

支持 Pi、Claude Code、Codex、OpenCode、Feynman。实际 argv 由适配器生成并记录在 Run；单次可用 `--backend` / `--model` 覆盖。Coding Hub 路由按角色难度使用 Pi / OpenCode 的 group 路由，direct 使用工具模型。只有 Pi 程序不存在且已配置 OpenCode 后备时才自动切换；等待权限或启动结果不明不切换。

Codex 使用 `--no-daemon`，OpenCode 使用独立 server 的 mini 交互界面和绑定当前 Run 的原生事件状态适配器，Feynman 使用新会话及指定研究 workflow。Worker 通过 hc 的 parent 关系归属于 PM，默认不创建额外 Tab，原生通知保持启用。保留原工具权限与认证；凭据不写入账本或 argv。

新团队的 Worker 默认独立 worktree，记录 baseCommit 和分支；未提交改动不会复制。旧配置在下一次派发写任务时也解析为独立 worktree；已有执行目录不变。Research 在独立持久输出目录工作，参考仓库路径另行提供。只读角色是行为契约，不是系统权限沙箱。

`worker --project PROJECT --item TASK --revision REV --role ROLE` 使用冻结的角色配置；`--tier` 可覆盖难度。自定义 `--command-json` 必须包含一个独立 `{context}`，直接传 argv、不经 shell；实际工具与模型以该命令为准，不能声称命中了默认模型。

## 研究契约

研究前先用 `search --project PROJECT --query TEXT` 检索已有报告，明确待支持的决策、范围、适用条件及停止条件。关键输入用任务 `inputArtifactRefs` 指向具体版本。

Research 默认 `--workflow deepresearch`。`autoresearch` 必须在任务 `researchContract` 保存经用户确认的 objective、metric、unit、direction、benchmark argv、allowedPaths、environment、maxIterations、userConfirmation；没有明确 benchmark 和迭代上限不启动。

回报使用 kind=progress/question/blocked/submitted/failed，并提供必要的 phase、nextAction、checkpointAt。问题明确 recipient=pm 或 user。退出、idle、done 都不是验收。

复杂成果通过 report.artifacts 中的 bundle 发布，`operations` 提供字段。保留 Feynman 原始目录和文件，用 role 标用途：

- Deepresearch：plan、draft、cited、brief、provenance。
- Autoresearch：summary、benchmark、iterations、changelog、brief、provenance。保留 baseline、全部尝试、seed、失败与 keep/revert 决定。

关键 claim 记录来源 reference、locator、accessedAt、验证状态、note 与 limitations。结构校验不能替代来源和论证核验。大型数据留在持久存储，以 external 清单记录位置、内容标识、大小及验证状态。

PM 先 `artifact.review`，再接受任务；`artifact.disposition` 另记采用、暂缓或不采用及理由。负面研究也可通过核验。`artifact.followup` 创建带版本来源的待办，不直接启动任务。过时或被替代结论用 `artifact.validity` 标记，保留历史版本与新证据。
