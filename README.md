# AI 数据分析助手（ChatBI）后端

基于 FastAPI 的 AI 数据分析助手后端。用户上传 CSV / Excel 数据集并用自然语言提问，系统完成 **结构化意图 → 受控 Pandas 计算 → 图表规格 → 结论生成**，返回图表、结果表与自然语言结论。

## 已实现能力

- 邮箱 + bcrypt 注册登录、JWT 鉴权、资源归属隔离。
- CSV / CSV（UTF-8、GB18030）/ XLSX / XLS 上传、类型推断、schema 与样例值生成、Parquet 落盘、异步解析、重解析和删除清理。
- 仅处理结构化分析计划（聚合、分组、过滤、时间粒度、排序、行数上限），**不执行模型生成的任意代码**。
- 独立分析子进程：固定白名单操作、超时、内存/CPU 限制、禁用网络、禁止文件写入、输出规模与数值校验。
- 柱状图、折线图、饼图和表格图表规格，适配前端 ECharts。
- 多轮对话、历史消息、对话删除、SSE 进度流。
- AI 网关统一重试、开发环境本地降级、token 成本记账、用户月度预算拦截。
- Redis 用户级限流（Redis 不可用时开发环境降级为进程内限流）。
- 统一 `{code, message, detail}` 错误协议、请求 ID、访问日志、Prometheus 指标、AI 用量接口。
- Docker Compose、非 root/只读容器、CI、Alembic 迁移和完整测试。

## 环境要求

- Python 3.11（当前项目固定支持 `>=3.11,<3.12`）
- Docker 与 Docker Compose（推荐部署方式）
- Redis 7（Compose 已包含；本机开发不可用时自动使用进程内限流）
- 托管大模型 API（可选，OpenAI Chat Completions 兼容；未配置时开发/测试环境使用确定性本地规则）

## 本地启动

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe scripts\configure_local_env.py
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

启动后访问：

- 中文操作台（普通用户）：<http://127.0.0.1:8000/>
- Swagger UI（开发者）：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>
- Prometheus 指标：<http://127.0.0.1:8000/metrics>
- OpenAPI 文档：<http://127.0.0.1:8000/openapi.json>

默认 `AI_PROVIDER=auto`：未配置远程模型时，开发/测试环境使用本地确定性规则完成端到端闭环；生产环境必须配置托管模型。

## 核心 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/register` | 注册并返回 JWT |
| POST | `/auth/login` | 登录并返回 JWT |
| GET | `/auth/me` | 当前用户 |
| POST | `/datasets` | 上传 CSV / Excel（multipart） |
| GET | `/datasets` | 当前用户数据集列表 |
| GET | `/datasets/{id}` | 数据集详情与 schema |
| POST | `/datasets/{id}/reparse` | 重新生成 schema |
| DELETE | `/datasets/{id}` | 删除数据集、会话及文件 |
| POST | `/datasets/{id}/chat` | 问答，返回图表 + 数据表 + 结论 |
| POST | `/datasets/{id}/chat/stream` | SSE 分析进度与最终结果 |
| GET | `/conversations` | 当前用户会话列表 |
| GET | `/conversations/{id}/messages` | 会话历史 |
| DELETE | `/conversations/{id}` | 删除会话 |
| GET | `/account/ai-usage` | 当月 token、成本和预算 |
| GET | `/metrics` | Prometheus 指标 |

除注册、登录、健康检查和指标外，所有接口需要 `Authorization: Bearer <JWT>`。完整请求/响应模型及在线调试见 `/docs`。

## 配置与密钥

配置通过环境变量或项目根目录的 `.env` 读取，完整字段见 `.env.example`。

- 默认本地 SQLite 为 `var/chatbi.db`，数据本体位于 `var/datasets/`。
- 生产环境必须设置至少 32 字符的 `JWT_SECRET`；默认开发值和示例占位值会被拒绝。
- `AI_API_KEY`、`JWT_SECRET` 使用 `SecretStr`，不会出现在设置 repr 或常规日志中。
- `.env`、数据库、上传文件、Parquet 文件和日志均已加入 `.gitignore`。
- 应用启动时创建数据目录，但不会自动建表；本地启动前执行 `alembic upgrade head`。

远程模型配置示例：

```dotenv
APP_ENV=production
AI_PROVIDER=openai_compatible
AI_API_BASE_URL=https://your-provider.example.com/v1
AI_API_KEY=your-secret
AI_MODEL=your-model-name
AI_INPUT_COST_PER_MILLION_USD=0.5
AI_OUTPUT_COST_PER_MILLION_USD=1.5
AI_MONTHLY_BUDGET_USD=20
```

`AI_API_BASE_URL` 应指向包含 `/chat/completions` 的兼容 API 前缀，例如 `https://host/v1`。

生成 JWT 密钥：

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 典型调用流程

```powershell
# 1. 注册，复制 access_token
$register = Invoke-RestMethod -Method Post http://localhost:8000/auth/register `
  -ContentType "application/json" `
  -Body '{"email":"demo@example.com","password":"correct horse battery"}'
$headers = @{ Authorization = "Bearer $($register.access_token)" }

# 2. 上传数据集
$dataset = Invoke-RestMethod -Method Post http://localhost:8000/datasets `
  -Headers $headers -Form @{ file = Get-Item .\sales.csv; name = "销售数据" }

# 3. 等待状态为 ready 后提问
$answer = Invoke-RestMethod -Method Post "http://localhost:8000/datasets/$($dataset.id)/chat" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"question":"近6个月各区域的销售额趋势如何？"}'
$answer.chart_spec
$answer.conclusion
```

解析是后台任务；上传后如状态仍为 `parsing`，请稍后重新查询 `/datasets/{id}`。

## 数据库迁移

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

初始迁移创建 `users`、`datasets`、`conversations`、`messages`；第二个迁移增加消息分析计划、数据集错误信息与 `ai_usage` 成本记录。

## 测试与质量

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
node --test tests\frontend
.\.venv\Scripts\python.exe scripts\smoke_health.py
.\.venv\Scripts\python.exe scripts\smoke_e2e.py
.\.venv\Scripts\python.exe scripts\verify_all.py
```

`verify_all.py` 默认派生独立后台进程，完成后查看 `verify_report.json`；如需在当前终端前台运行，使用 `scripts\verify_all.py --foreground`。`smoke_health.py` 只验证服务启动；`smoke_e2e.py` 使用临时数据库启动真实 Uvicorn，完成注册、上传、解析、问答、SSE、历史、用量、指标和删除全流程，不会污染本地数据。

测试覆盖认证、错误协议、CSV/Excel 解析、类型推断、ORM 迁移、用户隔离、AI 网关降级与配额、完整问答、SSE、图表、路径穿越、沙箱环境隔离、非法结果拦截、限流和指标。CI 在 `.github/workflows/ci.yml` 中执行 Ruff、pytest、Compose 校验和 Docker 构建。

## Docker Compose

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 保留现有 .env；生产环境修改 JWT_SECRET、模型与预算
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

容器特性：

- API 以非 root 用户运行，根文件系统只读，`/data` 为持久化卷，`/tmp` 为受限 tmpfs。
- 丢弃全部 Linux capabilities，启用 `no-new-privileges`，限制内存和 PID 数量。
- Redis 不暴露宿主机端口，仅通过 Compose 内部网络访问。
- API 启动前自动执行 `alembic upgrade head`。

停止服务：

```powershell
docker compose down
```

如需同时删除数据和 Redis 卷：

```powershell
docker compose down -v
```

## 可观测与成本

- `GET /health`：进程存活检查，Compose 使用该端点。
- `GET /metrics`：Prometheus 指标，包含 HTTP 请求量/延迟、AI 调用结果与累计估算成本。
- `GET /account/ai-usage`：当前用户本月调用数、token、成本和剩余预算。
- 日志包含请求 ID、路径模板、状态码、耗时和 AI 调用计量；不记录密码、JWT、API Key 或完整上传内容。
- 生产部署建议将指标接入 Prometheus/Grafana，并对 5xx、AI 失败率、限额拦截和成本突增告警。

## 安全设计

1. 模型只输出经过 Pydantic 校验的 `AnalysisPlan`，不能输出可执行代码。
2. 后端只按白名单聚合/过滤/分组操作执行，数据集列名不进入 `eval`、SQL 或动态 import。
3. 计算在独立进程中运行，超时终止；Linux 下设置 CPU/内存上限；禁用 socket 与文件写入。
4. 结果行数、列数、字符串长度、数值有限性和数值范围均再次校验。
5. 每次数据集、会话、消息和用量查询均强制 `user_id` 归属；跨用户访问统一返回 404。
6. 上传文件名被丢弃，只使用服务端 UUID 路径，并阻止存储根目录之外的路径穿越。
7. 生产环境拒绝开发 JWT 密钥和本地 AI 降级路径。
8. 用户级限流和月度 AI 预算防止滥用；失败调用也写入用量审计记录。

更完整的威胁模型、评测基线和运维说明见 [安全设计](docs/SECURITY.md)、[分析评测基线](docs/EVALUATION.md) 和 [运维手册](docs/OPERATIONS.md)。不写代码的用户请直接看 [使用手册](docs/USER_GUIDE.md)。

## 项目结构

```text
app/
├── api/              路由、依赖、中间件、错误处理
├── core/             配置、JWT、限流、日志、指标
├── db/               SQLAlchemy 引擎、会话、基类
├── models/           用户、数据集、会话、消息、AI 用量
├── schemas/          Pydantic 输入输出与结构化计划
├── services/         解析、AI 网关、计划校验、沙箱、图表、编排
├── static/           中文操作台（HTML/CSS/JS 与本地 ECharts）
└── main.py           FastAPI 应用入口
migrations/           Alembic 迁移
scripts/              健康和端到端验收脚本
tests/                单元、集成、安全、前端与部署配置测试
docs/                 架构、安全、运维文档
```

## 已知边界

- SQLite + 单机文件存储适用于 MVP；多实例部署前应迁移到 PostgreSQL 与对象存储。
- 本地规则 AI 仅用于开发和测试，复杂问题准确率有限；生产应配置托管模型并通过评测集回归。
- Redis 不可用时开发环境使用进程内限流；多进程生产环境必须保证 Redis 可用。
- 图表规格为 ECharts 友好结构，内置中文操作台会在本地直接渲染图表。
- Docker Desktop 已安装；WSL2 已完成初始化，Compose 容器构建、启动及容器内 E2E 均已验证。

## 里程碑

1. M0：项目初始化、CI、迁移、配置（已完成）。
2. M1：认证、AI 网关、解析、受控分析、图表与结论（已完成）。
3. M2：多轮对话、SSE、历史管理、数据隔离、错误规范、结果校验（已完成）。
4. M3：可观测、成本配额、限流、安全测试（已完成基线）。
5. M4：容器安全加固、部署与运维文档（已完成代码交付；灰度策略需结合目标平台执行）。
