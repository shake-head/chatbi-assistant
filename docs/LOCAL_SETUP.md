# 本机环境

## 当前 Windows 环境

- Python 3.11 虚拟环境：`.venv`
- SQLite：`var/chatbi.db`，迁移已应用
- Redis 兼容服务：Memurai Developer，Windows 服务名 `Memurai`，监听 `127.0.0.1:6379`
- API：当前通过 Docker Compose 运行，`http://127.0.0.1:8000`
- Docker Desktop：已安装并运行，CLI 位于 `C:\Program Files\Docker\Docker\resources\bin`
- WSL2：已初始化，默认发行版 `docker-desktop`
- PowerShell：CurrentUser 执行策略为 RemoteSigned；VS Code 工作区终端使用 `PowerShell (No Profile)` 避免用户 profile 报错

## 本地 API

启动并等待健康检查：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start_local.ps1
```

停止：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\stop_local.ps1
```

日志：

- `var/server.stdout.log`
- `var/server.stderr.log`

Redis 服务：

```powershell
Get-Service Memurai
Start-Service Memurai
Stop-Service Memurai
```

## Docker

安装和初始化已完成。日常启动顺序：

1. 打开 Docker Desktop。
2. 等待 Engine running。
3. 在项目目录运行 `docker compose up -d`。

由于当前网络无法直连 Docker Hub，已在本机 `%USERPROFILE%\.docker\daemon.json` 配置 Docker Hub 镜像源：

```json
"registry-mirrors": [
  "https://docker.1ms.run",
  "https://docker.xuanyuan.me",
  "https://docker.m.daocloud.io"
]
```

同时本机 `.env` 设置了：

```dotenv
PYTHON_BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/python:3.11-slim
```

Dockerfile 默认仍使用官方 `python:3.11-slim`，因此仓库在其他网络环境无需依赖华为云镜像。

修改前的配置备份为 `daemon.json.before-mirror.bak`。镜像站属于第三方分发渠道，仅用于当前本地环境；生产构建应使用可信镜像仓库并锁定镜像 digest。

Docker 引擎与 WSL2 已验证可用，Compose 已构建并启动成功：

- API 容器：healthy，8000 端口
- Redis 容器：healthy
- 容器内完整 API E2E：通过

Compose 验收可在代码变更后重新运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\launch_docker_up.ps1
```

完成后查看 `docker-up-report.json`；容器健康后再执行：

```powershell
.\.venv\Scripts\python.exe scripts\verify_docker_api.py
```

后者会直接通过 8000 端口验证注册、上传、问答、SSE、AI 用量、指标和删除，并写入 `docker-api-report.json`。

注意：Docker API 也使用 8000 端口。启动 Compose 前先执行 `scripts\stop_local.ps1`，避免端口冲突。

若重启后 `wsl --status` 仍提示虚拟化未启用，需要进入主板 BIOS/UEFI，开启 Intel VT-x / Virtualization Technology（本机 CPU 为 Intel i7-14650HX）。

重启后可用以下脚本自动启动 Docker Desktop 并等待引擎就绪：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\post_reboot_docker.ps1
```

脚本会输出 WSL 状态、Docker 版本和 Compose 版本；引擎未就绪时返回非零退出码。

## 配置

`.env` 已生成本地开发用 JWT 密钥。可用以下命令重新检查且不输出密钥：

```powershell
.\.venv\Scripts\python.exe scripts\diagnose_startup.py
```

报告写入 `startup_report.json`。
