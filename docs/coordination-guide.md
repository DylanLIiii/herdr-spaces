# PM 配置、协调与研究成果

本指南对应 0.4.0。项目仍使用 Herdr 原生 Agent 终端；Spaces 保存项目状态、配置、协调事件和成果。账本位于项目机器，不同步第二份到桌面。

## 首次使用：先指定 PM

1. 右键 Herdr 中的 Agent，选择「指定 / 交接项目 PM」；或从 Project 空状态进入。
2. 选择已有项目，或填写项目名、目标和目录。高级设置可选自定义 PM 工作指南。
3. 点击「绑定 PM 并交代配置」。空闲 PM 收到配置 Skill 的读取指引；忙碌时先保留绑定，稍后发送。发送结果不明时先查看原终端，不自动重复发送。
4. **指定的 PM 读取 `herdr-spaces-setup`，询问是否现在开始配置。** 选择稍后会保留绑定；之后在 PM 中说「继续配置」即可。
5. PM 检查已有环境、只询问缺失项，给出角色、模型、写入隔离、成果位置和自动跟进方案。用户确认具体方案后保存并验证。

配置状态：待开始 → 配置中 → 待验证 → 就绪。暂缓、中断或交接保留答案、草案、确认版本与验证结果。PM 绑定成功、指引已发送、模型已读取、配置已保存、能力已验证分别处理。Skill 提示本身不保证模型遵守；状态写入通过 CLI 校验。

已有项目可继续使用原 `subAgent {backend, model}` 配置。迁移不会假称已经完成新配置，也不会修改正在运行的任务。自定义 PM Skill 仍通过独立的 `skill --setup` 入口获得配置引导。

## PM 配置接口

PM 使用 context 提供的实际 CLI 前缀。以下以 `herdr-project` 为例：

```sh
herdr-project show --project PROJECT
herdr-project skill --project PROJECT --setup
herdr-project capabilities
herdr-project team-template --template mixed --routing direct
herdr-project operations
```

`capabilities` 仅探测本机工具安装，不读凭据、不调用模型。认证、模型、研究检索与回报状态明确显示为未验证。可选模板为 development / research / mixed；routing 可选 direct / coding-hub。

每次修改先读取项目 revision，再通过 `apply --revision REV --file REQUEST.json` 提交。配置操作包括：

| 操作 | 作用 |
| --- | --- |
| `setup.invite` | 记录 PM 已读取配置 Skill 并发起询问 |
| `setup.begin` | 记录用户同意开始或继续及其来源 |
| `setup.defer` | 暂缓并保留进度 |
| `setup.answer` | 保存一项答案与下一步 |
| `setup.draft` | 校验并保存完整配置草案 |
| `setup.confirm` | 按 draftRevision 应用用户确认的具体方案，生成配置版本 |
| `setup.check` | 记录当前配置版本的真实或 fixture 检查结果 |
| `setup.finish` | 所需检查具备 observed / passed 证据后进入就绪 |

`show` 中 `setup.requiredChecks` 列出当前配置要求。Fixture 通过不能证明真实账户、模型、检索或服务已可用。工具登录通过工具自身认证完成，密钥不进入配置草案或答案。验收证据是 PM 提供的事实记录，CLI 能核对状态和版本，不能自动证明自由文本证据真实。

配置默认采用一个 PM，以及按需启动的 Worker、Explore、Librarian、Reviewer、Research、Oracle。角色与任务难度分开；PM 使用 Sage / Apex，研究使用 Feynman 工作流。Coding Hub 模板使用 Pi 路由组和可用 OpenCode 后备；direct 允许各工具自己的模型。只有 Pi 二进制缺失且已配置 OpenCode 后备时才自动切换，发生启动结果不明或等待输入时保留原执行。

PM 角色的配置是团队工作说明和路由偏好；绑定的现有 PM 进程不会被强制切换模型或重启。

## 持续跟进

用户确认启用自动跟进的配置后，CLI 在项目机器启动普通后台服务。它不调用模型、不派发新任务、不接受成果；只检查约定的检查点，并将需要判断的事件送到 PM。

```sh
herdr-project service status
herdr-project service start
herdr-project service stop
herdr-project service run   # 前台运行，适合已有进程管理器
herdr-project inbox --project PROJECT
```

服务由进程锁保证单实例，独立于窗口存活。机器重启或服务被终止后，运行 `service start` 恢复；也可以由已有 launchd/systemd 等进程管理器运行 `service run`。安装器不修改用户的系统服务配置。`status` 的 `live` 来自锁状态，历史状态不是存活证明；检查结果与错误包含在状态记录中。日志位于数据根 `logs/coordinator.log`。

Worker 回报与收件箱同事务提交。普通 progress 只更新待处理进度，不单独打扰 PM；问题、阻塞、提交、失败与检查点会通知。PM 忙碌或等待权限输入时保留排队事件，服务遇到连接失败会退避，最多一分钟后再检查。

收件箱状态与任务状态独立：

```text
queued → sending → sent → acknowledged → handled
              ↘ uncertain
```

原始终端发送无法承诺 exactly-once。服务崩溃时正在发送的记录恢复成 uncertain；结果不明不自动重发。PM 可直接读取并处理，或核对实际终端后显式使用 `inbox.retry`。`sent` 只证明发送完成，不说明 PM 已读或已处理。

PM 读取后用 `inbox.acknowledge {ids}` 确认接收；核验、返工或解阻塞后用 `inbox.handle {ids,note}` 记录处理依据。所有写入仍要求当前 Main 身份、generation、项目 revision 和唯一 requestId。交接保留事件与既往发送记录，将未处理事项转给新代次；旧 PM 写入被拒绝。

检查点只生成待判断事件，不自动失败、取消或重启任务。PM 检查现有 Run、最近有效进展和证据，再决定下一步。人需要回答的问题必须结构化标明 recipient=user；其他核验交给 PM。

## 角色派发与隔离

```sh
herdr-project worker --project PROJECT --item TASK --revision REV --role worker
herdr-project worker --project PROJECT --item STUDY --revision REV --role research
herdr-project worker --project PROJECT --item REVIEW --revision REV --role reviewer --tier sage
```

任务依赖与已有授权须先满足。可单次覆盖 backend / model / tier；Research 另可指定 `--workflow deepresearch|autoresearch`。`--command-json` 保留自定义执行与 fixture 能力，实际 argv 会留在 Run。

- 新团队配置的 Worker 默认从当前 HEAD 创建独立 worktree 和 `spaces/<run-id>` 分支；未提交的主目录改动不会自动复制。
- 旧配置默认保持项目 cwd，但同一实际目录只能有一个 live/uncertain 写手，包括不同项目指向同一目录的情况。
- Explore、Librarian、Reviewer、Oracle 以只读职责使用项目目录；这是角色约束，不是 OS 沙箱。
- Research 的 cwd 是项目持久输出目录，参考仓库路径另行提供。
- Run 固化角色、工具、请求模型/路由、配置版本、Skill 哈希、输入产物版本、cwd、branch、baseCommit 和 outputRoot。无法观测的实际模型为 null，不冒充路由实际命中的模型。
- 工作目录准备失败保留 Run 和错误，进入待 PM 处理；启动响应不明保留预留与工作目录，先 reconcile。

Autoresearch 必须有经用户确认的 `researchContract`：objective、metric、unit、direction、benchmark argv、allowedPaths、environment、maxIterations、userConfirmation。通过 `item.update` 保存；缺少契约或迭代边界时拒绝启动。

## Worker 回报

```json
{
  "requestId": "report-unique-id",
  "kind": "progress",
  "text": "完成来源核对，正在整理适用限制。",
  "phase": "核对来源",
  "nextAction": "提交引用稿与 provenance",
  "checkpointAt": "2030-01-01T12:00:00Z",
  "waitingOn": null
}
```

kind 为 progress / question / blocked / submitted / failed。Question 需要 `{text,recipient,recommendation?}`，recipient 为 pm 或 user；waitingOn 可为 pm / user / dependency / environment / null。旧 `submitted=true` 保持兼容；submitted 进入任务 review，无法自行 accepted。

## 研究产物发布

产物默认保存在 `<data-home>/projects/<project-id>/artifacts/`；确认配置时可指定唯一 artifactRoot。每个 Run 的可变输出在 `work/<run-id>/`，发布结果在 `published/<artifact-id>/`。

可直接登记旧的绝对文件路径，也可提交 bundle。产物 id 标识一个不可变版本；familyId 关联同一成果系列，previousVersionId 指向前版。发布时复制清单中的文件、核对哈希、生成 manifest，再原子移动到最终目录。只有完整发布成功才入账；数据库事务回滚留下的同 id/同内容发布可重试复用，不覆盖。

```json
{
  "id": "study-v1",
  "familyId": "study",
  "version": "1",
  "title": "协调机制研究",
  "kind": "research",
  "sourceRef": "任务简报及原始来源",
  "bundle": {
    "root": "/absolute/research/output",
    "entrypoint": "brief.md",
    "workflow": "deepresearch",
    "files": [
      {"path": "plan.md", "role": "plan"},
      {"path": "draft.md", "role": "draft"},
      {"path": "cited.md", "role": "cited"},
      {"path": "brief.md", "role": "brief"},
      {"path": "provenance.md", "role": "provenance"}
    ],
    "claims": [],
    "external": []
  }
}
```

将该对象放入 Worker `report.artifacts[]`，或由 PM 使用 `artifact.add`，后者还需 workItemId。文件名可以保持 Feynman 原有 `.plans`、`.drafts`、outputs 等结构，role 标注用途即可。

Deepresearch 必须有 plan / draft / cited / brief / provenance。Autoresearch 必须有 summary / benchmark / iterations / changelog / brief / provenance；iterations 包含全部尝试、基线、指标和失败，不仅最佳结果。结构校验只检查交付清单，语义充分性仍由 PM / Reviewer 核验。

关键 claim 可包含 id、text、sources（reference、locator、accessedAt）、verification、note 和 limitations。verification 可为 verified / unverified / contradicted。小报告无需将每句话建模为 claim。

单包上限 200 个文件、100 MiB；登记文件和 manifest 上限 10 MiB。大数据在 external 清单记录 location、contentId、size、status 和 note，数据保持在持久存储，不复制进账本。清单状态不等于下载或内容验证。

### 核验、采用与有效性

| 维度 | 操作 | 状态 |
| --- | --- | --- |
| 报告质量 | `artifact.review` | review / accepted / rejected |
| 项目采用 | `artifact.disposition` | adopted / deferred / declined，附理由并生成决策 |
| 当前适用性 | `artifact.validity` | current / stale / superseded，附理由及可选替代版本 |

采用要求已核验、当前且完整的产物。严谨的负面报告可以 accepted，同时建议 declined。accepted 只表示 PM 的审阅结论，哈希只证明内容未变，不自动证明来源支持论点。

`artifact.followup` 创建或复用一个引用精确产物版本的待办；不会直接派发。`decision.add` 可带 artifactRefs，任务可带 inputArtifactRefs。研究开始前用 `search --project PROJECT --query TEXT` 检索已有结果。检索是有界元数据/文本匹配，没有语义索引，也不创造新事实。

`read --artifact ID --member RELATIVE_PATH --offset BYTES` 支持产物成员和分段文本。非文本附件明确提示使用对应工具；当前不内嵌 PDF 阅读器。正文最多每次 64 KB，nextOffset 用于续读。

## 原生界面

任务 / 会话 / 成果保持原有位置与 1/2/3 快捷导航。首页先显示当前阶段或 PM 判断；只有结构化 user 问题进入「需要你」，其余需要协调的任务进入「待 PM 处理」。任务详情包含下一动作、检查点、依据和执行回报。

成果页支持标题/结论/来源筛选，以及报告正文搜索。点击「展开阅读」进入较宽的原生阅读窗口，查看正文、关键来源、过程文件、版本和关联决策；可以回到 PM 讨论或验证建议。窗口固定原项目来源，不随其他终端焦点切换到另一本账。

配置窗口展示 Skill 流程的进度、团队与真实验证状态；「进入 PM 继续配置」回到同一项目 PM，不从 UI 静默启动模型任务。

离线时保留上次数据并显示读取时间。客户端读取继续使用项目机器的 Core/账本来源校验；不将远端路径解释成本机文件。
