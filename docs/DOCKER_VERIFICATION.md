# Docker 环境验收

## 本机前置条件

- Windows 11 + WSL2
- Docker Desktop 4.99.0
- Docker Engine 29.9.3
- Docker Compose v5.7.0
- WSL 默认发行版 `docker-desktop`
- Docker Hub 不可直连；Dockerfile 默认仍是 `python:3.11-slim`，本机 `.env` 通过 `PYTHON_BASE_IMAGE` 指向 AWS 官方镜像缓存 `public.ecr.aws/docker/library/python:3.11-slim`
- 同时配置了 `docker.1ms.run`、`docker.xuanyuan.me`、`docker.m.daocloud.io` 三个 Docker Hub 镜像源作为备用

## 验收命令

```powershell
docker info
docker compose config --quiet
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\launch_docker_up.ps1
```

`launch_docker_up.ps1` 在独立后台进程中执行：

1. 校验 Compose 配置。
2. `docker compose up --build -d`。
3. 最多等待 180 秒调用 `http://127.0.0.1:8000/health`。
4. 输出服务状态和构建日志尾部到 `docker-up-report.json`。

## 容器 API 全链路

Compose 健康后运行：

```powershell
.\.venv\Scripts\python.exe scripts\verify_docker_api.py
```

该脚本直接访问容器 API，不启动本地 Uvicorn，覆盖：

- 注册与 JWT。
- 数据集上传、后台解析、schema。
- 结构化计划与容器内分析子进程。
- 图表、结论、多轮历史和 SSE。
- Redis 限流依赖路径。
- AI 用量和 Prometheus 指标。
- 数据集与文件删除。

结果写入 `docker-api-report.json`。

## 实际验收结果

- Docker Compose 配置校验：通过。
- 应用镜像构建：通过（首次使用华为云缓存的 `python:3.11-slim` 基础镜像）。
- `chatbi-api-1`：healthy，映射 8000。
- `chatbi-redis-1`：healthy。
- 容器内完整 E2E：通过，9 项检查全部为 true。
- 图表：柱状图，系列 `amount合计`，结果 3 行。
- SSE：收到 status、plan、result、final 事件。
- 数据集删除和存储清理：通过。

容器内曾发现并修复两个 Linux 专属问题：

1. PyArrow 延迟导入 SSL 时不能替换整个 `socket.socket` 类；网络防护改为只拦截 `connect/connect_ex/getaddrinfo`。
2. Pandas/PyArrow 启动后已有约 1.2GB 虚拟地址基线；`RLIMIT_AS` 改为“基线 + 配置额度”，硬 RSS 上限仍由容器 cgroup 约束。

## 注意事项

- 启动 Compose 前必须停止本地 8000 端口服务：`scripts\stop_local.ps1`。
- Memurai 可继续运行在宿主机 6379，Compose Redis 不映射宿主机端口，因此不冲突。
- 本地镜像源只用于开发验证；生产应使用可信 Registry、固定 digest、镜像扫描和签名验证。
- 如果 Docker Hub 恢复可直连，可移除 `%USERPROFILE%\.docker\daemon.json` 中的 `registry-mirrors` 并重启 Docker Desktop。
