# SubAgent 的 Coding 工具与模型

每个项目保存一份 `subAgent` 设置，含 `backend` 和 `model`。在 Project Leader 设置窗口中选择 Coding 工具并填写模型；留空模型表示使用该工具本机的默认模型。选择工具后需确认目标机器安装了对应程序，并已按该工具自身的流程完成登录或提供凭据。不要把密钥写进项目账本或启动参数。

| Coding 工具 | backend | 默认启动 argv |
| --- | --- | --- |
| Pi | pi | `["pi", "--model", "MODEL", "{context}"]` |
| Claude Code | claude | `["claude", "--model", "MODEL", "{context}"]` |
| Codex | codex | `["codex", "--no-daemon", "--model", "MODEL", "{context}"]` |

Codex 使用 `--no-daemon` 保持独立终端身份，避免共享进程继承错误的 PM/Worker 环境。自定义 Codex argv 也应保留此参数。

未指定模型时省略 `--model MODEL`。模型标识必须是所选工具支持的值；Pi 可使用 provider/model 标识。模型清单、可用性和登录状态由各 Coding 工具提供，Herdr Spaces 不验证模型服务端权限。

## 配置引导

1. 使用 `show` 检查项目的 `subAgent`。询问并补全尚未明确的 Coding 工具、模型和所需的文件读取、修改、终端命令能力。
2. 通过设置窗口保存默认值。CLI 也可用 `bind --terminal TERMINAL --core-scope CORE --project PROJECT --replace-generation GENERATION --worker-backend pi --worker-model MODEL` 保存当前 PM 的设置；代次从 `show` 获取。切换 PM 使用相同命令并指定新终端。
3. Worker 在项目所属机器和项目 cwd 中运行。确认该机器可找到 Coding 程序，并在其自身界面配置文件编辑、shell、网络及审批策略。现有工具权限保持有效，Herdr Spaces 不添加跳过确认或禁用沙箱的参数。
4. 启动前明确派发授权、范围、验收标准及证据路径。跨 Agent 并行修改代码时安排隔离目录；启动器不会自动创建 worktree。

## 启动与覆盖

`worker --project PROJECT --item WORK_ID --revision REVISION` 使用已保存的工具和模型。

单次覆盖可使用 `--backend claude --model MODEL`。若切换到其他 Coding 工具且省略模型，则使用新工具默认模型，避免把原工具的模型标识传给它。

需要自定义工具集、恢复参数或隔离工作目录时，先按对应 Coding 工具文档确认参数，再使用 `--command-json '["PROGRAM","OPTION","{context}"]'`。自定义 argv 完全取代默认命令，不自动附加模型；`{context}` 必须作为独立参数出现一次。参数直接传给程序，不经过 shell 解释。

保存配置不会启动 Worker。启动时检查程序是否存在；模型是否有效、权限是否够用需以所选工具的实际结果为准。失败应记录并纠正配置，不能把进程结束当成交付完成。
