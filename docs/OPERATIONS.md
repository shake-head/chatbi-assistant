# 运维手册

## 1. 启动前检查

1. `.env` 已从 `.env.example` 创建，且不在版本库。
2. 生产 `APP_ENV=production`，`JWT_SECRET` 已替换为至少 32 字符随机值。
3. 生产已配置 `AI_PROVIDER=openai_compatible`、模型地址、模型名和 API Key。
4. 已设置输入/输出 token 单价与 `AI_MONTHLY_BUDGET_USD`。
5. Redis 可达；不要依赖生产环境进程内降级。
6. `DATA_DIR` 位于持久化磁盘或卷，容量足够保存 Parquet 和 SQLite。
7. `/metrics` 只对监控网络开放。

## 2. 本地运行

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

后台解析使用 FastAPI `BackgroundTasks`，单进程内执行。生产多实例前应改用独立任务队列。

## 3. 容器运行

```powershell
Copy-Item .env.example .env
# 编辑 .env
docker compose up --build -d
docker compose ps
docker compose logs -f api
```

API 容器启动时自动执行迁移。根文件系统只读，应用数据在命名卷 `chatbi_data`，Redis 数据在 `redis_data`。

升级：

```powershell
docker compose build api
docker compose up -d api
```

回滚应用镜像前注意数据库迁移的向后兼容性。当前数据库无破坏性回滚自动化，恢复优先使用备份。

## 4. 数据库迁移

```powershell
# 本地
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head

# 容器
docker compose exec api alembic current
docker compose exec api alembic upgrade head
```

迁移前备份：

```powershell
New-Item -ItemType Directory -Force .\backups
docker compose exec -T api python -c "import sqlite3; src=sqlite3.connect('/data/chatbi.db'); dst=sqlite3.connect('/data/chatbi.backup.db'); src.backup(dst); dst.close(); src.close()"
docker compose cp api:/data/chatbi.backup.db .\backups\chatbi.db
```

同时备份 `/data/datasets`。SQLite 与数据文件必须成对恢复，否则元数据与 Parquet 会不一致。

## 5. 监控

- `/health`：API 进程存活。Compose 每 10 秒检查。
- `/metrics`：
  - `chatbi_http_requests_total{method,path,status}`
  - `chatbi_http_request_duration_seconds`
  - `chatbi_ai_requests_total{operation,provider,status}`
  - `chatbi_ai_cost_usd_total{operation,provider}`
- 用户用量：`GET /account/ai-usage`。
- 日志检索字段：`request_id`、`http_request`、`ai_call`、`ai_attempt_failed`、`dataset_parse_failed`。

建议告警：

| 告警 | 条件 |
|---|---|
| API 5xx | 5 分钟错误率 > 2% |
| 延迟 | P95 > 10 秒 |
| AI 失败 | `status=failure` 连续 5 分钟上升 |
| 成本 | 用户或整体成本接近预算 |
| 限流 | `RATE_LIMIT_EXCEEDED` 突增 |
| 解析失败 | `dataset_parse_failed` 突增 |
| 存储 | 数据卷使用率 > 80% |

## 6. 常见故障

### API 启动失败：JWT_SECRET

生产环境使用默认值或少于 32 字符会被拒绝。生成新密钥并设置环境变量。

### AI_NOT_CONFIGURED

生产未配置远程模型。设置 `AI_PROVIDER=openai_compatible`、`AI_API_BASE_URL` 和 `AI_MODEL`。

### AI_SERVICE_UNAVAILABLE

远程模型超时或失败。检查提供方网络/配额；开发环境会降级本地规则，生产不会。

### ANALYSIS_TIMEOUT / ANALYSIS_EXECUTION_FAILED

检查数据规模、筛选条件和 worker 日志。可降低结果行数、提高超时，或增加容器内存。不要直接执行用户/模型提供的代码。

### 数据集一直 parsing

后台任务可能因进程重启丢失。调用 `POST /datasets/{id}/reparse` 从 Parquet 重建 schema；若 Parquet 不存在，需重新上传。

### 限流被触发

检查 Redis 可用性和用户请求量。阈值由 `AI_RATE_LIMIT_REQUESTS`、`UPLOAD_RATE_LIMIT_REQUESTS` 和窗口控制。

### 配额超限

`GET /account/ai-usage` 查看当月成本。必要时调整 `AI_MONTHLY_BUDGET_USD` 或等待下月重置。

## 7. 备份与清理

- 每次迁移或发布前备份 SQLite 与 `datasets`。
- 用户删除数据集时会删除元数据、会话和文件。
- 定期检查 `DATA_DIR/tmp` 是否残留；正常解析完成应删除临时文件。
- 不直接手改 SQLite 或 Parquet；通过 API/迁移维护一致性。

## 8. 容量与扩展

- MVP 单数据集建议 ≤ 100 万行，上传 ≤ 50 MB（可配置）。
- 单次结果默认最多 1000 行。
- SQLite 适合单实例；多实例前迁移 PostgreSQL。
- 共享文件系统不能替代对象存储；多实例需统一存储和 Redis。
- 后台解析在 API 进程内，大规模场景应迁移任务队列。

## 10. 一键验收

```powershell
.\.venv\Scripts\python.exe scripts\verify_all.py
```

脚本默认派生独立后台进程，顺序执行 Ruff、格式检查、pytest 和真实 HTTP E2E，将各步骤退出码、耗时和最后输出写入 `verify_report.json`；前台运行使用 `scripts\verify_all.py --foreground`。E2E 使用临时 SQLite 和临时数据目录，不污染本地数据库。

1. 在 CI 通过 Ruff、pytest、`docker compose config` 和 `docker build`。
2. 先备份数据库和数据文件。
3. 部署新镜像，观察健康检查、5xx、P95 和 AI 失败率。
4. 出问题优先切回旧镜像；若迁移不兼容，按备份恢复。
5. 灰度阶段建议按反向代理流量比例或独立实例验证，再全量。

当前仓库提供部署与安全基线；“灰度发布”需结合目标平台（Kubernetes、云平台或反向代理）配置，不在应用进程内模拟。
