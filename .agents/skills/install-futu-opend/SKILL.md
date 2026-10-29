---
name: install-futu-opend
description: 在本项目安装、启动和登录富途官方 OpenD，并验证本机网关与 Python SDK 的连接。默认命令行版，可询问是否改用可视化版；项目业务数据继续走现有接口。
metadata:
  version: 0.1.1
  author: Futu
  project_adaptation: financial-freedom
---

# 富途 OpenD 安装与登录

本 skill 基于[富途官方 OpenD Skills](https://openapi.futunn.com/futu-api-doc/intro/ai.html) 的 `install-futu-opend`。官方原文保存在 [upstream-install-skill.md](references/upstream-install-skill.md)，仅供版本比对，不作为本项目的执行指引；本项目只调整安装版本选择、登录方式和验证范围。**主要用途是安装和登录，业务数据继续通过本项目现有接口读取。**

## 选择与检查

先识别操作系统及架构，检查是否已有可用 OpenD、`127.0.0.1:11111` 监听和项目虚拟环境中的 `futu-api`。已有正常服务时直接进入验证，不重复安装。需要安装时，**默认官方命令行版**，可询问用户是否更希望安装可视化版；用户已明确选择则直接执行。未收到可视化版选择时继续命令行版。

官方包按系统下载：

| 系统 | 官方地址 |
| --- | --- |
| Windows | `https://www.futunn.com/download/fetch-lasted-link?name=opend-windows` |
| macOS | `https://www.futunn.com/download/fetch-lasted-link?name=opend-macos` |
| Ubuntu | `https://www.futunn.com/download/fetch-lasted-link?name=opend-ubuntu` |
| CentOS | `https://www.futunn.com/download/fetch-lasted-link?name=opend-centos` |

下载到独立临时目录；校验下载成功和压缩包内容。官方包可能同时含两种版本，必须按内部文件辨认：`FutuOpenD` / `FutuOpenD.exe` 与 `FutuOpenD.xml` 是命令行版；`OpenD-GUI` 的安装程序或 `.dmg` 是可视化版。不能仅看压缩包名。不要覆盖已有安装或执行包内未知脚本。命令行版保留完整程序目录、XML、`AppData.dat` 及依赖，在该目录启动：Windows 用 `FutuOpenD.exe`，Linux/macOS 用 `./FutuOpenD`；macOS 包也可能提供 `FutuOpenD.app/Contents/MacOS/FutuOpenD`。配置文件定位失败时按[官方命令行说明](https://openapi.futunn.com/futu-api-doc/opend/opend-cmd.html)传 `-cfg_file=绝对路径`。选可视化版时按官方包内安装程序操作，可参考本 skill 的 `scripts/install_mac.md`、`scripts/install_win.md`、`scripts/install_linux.md`；这些上游参考只适用于可视化版。

## 登录

从交互式终端启动命令行 OpenD，或打开可视化版。让用户**在 OpenD 自身**输入账号、密码、验证码并完成首次问卷和协议。官方 10.10 起默认进入交互登录；不要把密码、验证码、交易密码放进聊天、环境变量、XML、命令行、日志或仓库。不要代用 `-login_by_remember`，是否记住密码由用户在 OpenD 内选择。监听地址保持 `127.0.0.1`，默认 API 端口 `11111`。

## 验证与项目接入

只在项目虚拟环境缺少或不兼容 `futu-api` 时按 `requirements.txt` 安装对应版本；不要全局升级 Python 包，也不要安装上游 skill 附带的回测、绘图依赖。在项目根目录运行 `.venv/bin/python .agents/skills/futuapi/scripts/quote/get_global_state.py --json`（Windows 使用虚拟环境的 `python.exe`），检查 `qot_logined`、`trd_logined` 和 OpenD 版本；端口开放不等于登录成功。若用户需要，可用一次官方行情快照脚本作连通测试，不把它当成业务数据源。验证后回到本项目的 `/api/v1/providers/futu/status` 和现有页面确认数据链路。`FUTU_ENABLED` 控制行情，`FUTU_TRADE_ENABLED` 控制账户发现；二者与 OpenD 登录分开。macOS 的 `scripts/futu-host.py --ensure` 会在端口未监听时打开可视化版；使用命令行版时先启动 OpenD，再启动本项目。

本项目真实交易有自己的开关和限制，详见 `README.md`、`docs/BROKER_SETUP.md`。安装与登录流程不自动解锁交易，也不运行官方下单脚本。上游的版本戳 `~/.futu_skill_version` 只用于官方脚本提示，缺失不会阻止连接。
