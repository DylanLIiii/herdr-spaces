# 指定 Project Leader

## 为什么旧版出现安装错误

0.2 侧栏需要在目标机器找到 `herdr-spaces/runtimes/projects.json`，但把缺少登记的首次使用状态当成了普通执行错误，显示红色错误和 CLI 命令。缺少登记通常表示服务器未安装运行程序，也可能是安装名称或 Core 的 XDG 配置目录不同。它不代表项目数据丢失。

0.3 把这一步纳入用户的实际操作：在左侧 Agent 列表右键“设为 Project Leader…”，或使用右侧 Project 空状态按钮。进入设置后自动准备目标机器、列出已有项目，再绑定当前终端。

## 用户流程

![左侧 Agent 的 Leader 入口](onboarding/menu.png)

截图来自隔离的真实 Herdr 窗口，使用合成 Agent 测试数据。

- 选择正在使用的 Agent 终端，右键指定 Leader。
- 选择项目或新建项目，只填写名称、目标和目录；默认名称和目录来自该终端。
- “绑定并交代项目”保留原生会话，为它登记唯一的 Main 身份和当前代次。
- Agent 空闲且主动报告了 app 状态时，通过 Core 的 `send --if idle` 发送一次可见的项目说明，要求它读取 `context`。
- Agent 正在工作、等待确认，或只是普通 shell 时，绑定成功但不发送输入。界面保留“交代项目”入口，供用户在合适时机操作。不会使用 `--force`，不会轮询后自动替用户继续。
- 发送结果不确定时不自动重发，提示查看原生终端。重复点击绑定不会重复创建 Leader 或重复发送已确认的说明。

![原生项目设置窗口](onboarding/form.png)

已有其他 Leader 的项目只提供进入原终端，不能抢占。一个 terminal 也不能同时成为两个项目的 Leader，或把已登记的 Worker 改成另一个项目的 Leader。

## 自动准备的范围

桌面安装附带匹配版本的 Python 源码包和校验值。用户进入设置时，程序经 Herdr 的目标机器连接部署这一份代码。没有另开网络服务，不从 GitHub 下载浮动分支，不安装模型或依赖包。

自动部署目录：`${XDG_DATA_HOME:-~/.local/share}/herdr-spaces/runtime/<name>/<bundle-hash>/`。登记文件仍在目标机器的 XDG config 下。已有可兼容运行程序会直接复用；旧的、可检查的登记会保留它的账本目录，切换到新版本目录，旧运行程序不会被删除。登记无效或不能检查时不会覆盖。

自动准备不改用户的 PATH、shell 配置、后端 Hooks 或已有 `herdr-project` 命令。发给 Leader 的说明包含准确的 CLI 绝对路径。需要全局命令时仍可使用手动安装器。

## 现有终端的身份

被指定的终端在账本中标记为 `mode=attached`。它的 CLI 调用通过目标 Core 的持久 id、`HC_TERMINAL_ID`、终端绑定和当前 Main 代次解析身份。受管理的启动仍使用原有环境 token；无效或过期的 managed token 不会回退成附着身份。

绑定身份和 Agent 已理解规则是两个状态。UI 显示 Leader 不代表某个模型一定已经遵守了规则。普通 CLI 外的同用户 shell 仍具有本用户文件权限，终端身份不是操作系统安全隔离。

现有会话无法在进程中途补写父进程环境变量，因此没有假装为它安装 token。绑定后由项目 CLI 在目标机器解析终端身份，启动 Worker 时再为 Worker 分配自己的 token。Agent 自己绕过启动器开的子进程可能继承父终端身份；应使用项目 CLI 的 worker 接口，不能把它当成防恶意进程的沙箱。

Attached Leader 的空闲或 done 不触发退出。需要替换时，先在原生终端检查并明确结束旧终端，再 `reconcile`，之后从新终端重新指定；旧终端不会恢复为新一代 Leader。Managed Leader 的原有恢复规则保持。

## 从 0.1 / 0.2 更新

旧安装器拒绝覆盖，这是为了保留个人布局。可在桌面机器执行：

```sh
git pull
python3 scripts/install.py --name spaces-v03
herdr-app do layout.switch '{"name":"spaces-v03"}'
```

新布局包含自己的 Agents 和设置入口。默认账本目录不变，现有项目无需复制。远端同名 runtime 如果没有登记，首次设置会自动准备；需要读取原先自定义数据目录时，在新布局的 Project 和 Agents props 中使用一致的 `remotes` 配置（见 [远程说明](remote.md)）。不要把自定义数据目录留空后误当成原账本。

若远端仍使用原安装名 `projects`，可将新布局中 Project 与 Agents 的 `remoteName` 都设为 `projects`，自动准备会检查该登记并保留其账本路径。使用显式 `remotes.<machine>.command` 的管理员需自行更新那个入口；界面不会覆盖一个自定义命令。
