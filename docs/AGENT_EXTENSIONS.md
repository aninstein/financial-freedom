# Agent 扩展接入说明

普通投研对话默认由公开来源的 [DeerFlow](https://github.com/bytedance/deer-flow) 运行。应用只向它提供本轮授权的投研工具、已安装 Skill 的名称与描述，以及经筛选的 MCP 工具。扩展配置默认保存在私有数据卷 `/app/data/agent-extensions/`，不会进入 Git 或模型配置文件。可在私有 `.env` 设置 `AGENT_EXTENSIONS_DIR` 指定其他目录；Docker 部署时，该目录须挂载为 Web 与 DeerFlow worker 共用的持久卷。

## Skills

打开「数据与模型 → Skills」，粘贴公开 GitHub 仓库链接；一个仓库有多个 Skill 时填写 `SKILL.md` 中的 `name`。也可上传含 `SKILL.md` 的 ZIP。聊天中可以发送“安装 Skill `stock-research-executor`，来源 `https://github.com/owner/repository`”，或点击输入框下的 Skill ZIP 按钮。安装结果会显示在设置页。

系统读取 Skill 的 YAML 元数据并安装其目录文件。设置页显示名称、描述与声明所需工具；这些声明只用于核对依赖，不会自动授予权限。对话时，Agent 先看到名称和描述；相关任务可调用 `activate_skill` 读取完整 `SKILL.md`，随后用 `read_skill_file` 读取同目录中的小型文本参考文件。Skill 随附脚本不会自动运行，也不会获得 shell、数据库或交易权限。ZIP 有大小、文件数、路径与符号链接检查；请仍核对来源和说明内容。

无需使用第三方安装 CLI。若收到含专用 npm registry 的安装文字，应用只提取公开 GitHub 仓库与 Skill 名称，从公开仓库下载 ZIP；不会执行文字中的 shell 命令。此入口只安装到本应用的 DeerFlow；文字里的其他 IDE 目标参数不会改写外部目录。

## MCP

在「数据与模型 → MCP 连接」粘贴标准 `mcpServers` JSON，或在聊天中明确要求安装并粘贴 JSON。例如：

```json
{
  "mcpServers": {
    "research": {
      "command": "npx",
      "args": ["-y", "@example/research-mcp"],
      "env": {"API_TOKEN": "在私有设置中填写"}
    }
  }
}
```

支持 `npx`、`uvx`、`python`、`python3`、`node` 的 stdio 连接，或带 `url`、可选 `headers` 的 Streamable HTTP 连接。远端 URL 需使用 HTTPS；本机回环地址可使用 HTTP。保存后服务端会连接并列出工具，设置页可重新连接、移除或查看连接状态。连接命令以应用容器为工作目录运行；只有用户明确添加的服务会启动。

默认只有服务声明为只读的工具会进入投研聊天。设置页可对单个连接显式启用可写工具；这个操作要求重新验证密码。可写工具可能改变外部系统，应先检查其权限。应用内的实盘交易路由仍不作为 Agent 工具。MCP 工具输出是不可信数据，不能修改 Agent 权限。

MCP 凭据仅写入权限为 `0600` 的私有配置文件。通过聊天安装时，原始 JSON 只发给本机服务端安装入口；聊天记录显示“添加 MCP 连接”，不会保存原始 JSON，也不会转发给模型。若要修改凭据，在设置页提交新配置。备份数据卷时应把它当作秘密处理。

## 运行与排查

修改源码或依赖后运行 `./scripts/docker-up.sh` 构建并启动 Web 与 DeerFlow worker。访问 `/api/v1/ai/status` 检查 `runtime=deerflow` 和 `runtime_ready=true`；在设置页确认扩展状态。若 MCP 连接失败，先检查命令、包名、网络和凭据，再点击“重新连接”。公开 GitHub 不可达时可上传已核对的 Skill ZIP。

普通投研只能调用本轮暴露的工具，账号读取仍需本轮显式选择。扩展不能绕过模拟盘的单轮授权与服务端交易校验。
