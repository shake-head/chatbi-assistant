# 架构说明

## 1. 分层

```text
HTTP / SSE
  └─ FastAPI 路由、JWT、限流、统一错误
      └─ 应用服务
          ├─ 数据集：上传、解析、schema、删除
          ├─ 分析：意图 → 校验 → 沙箱 → 图表 → 结论
          └─ 会话：多轮历史、消息持久化
              └─ 能力层
                  ├─ AI 网关：重试、降级、记账、配额
                  ├─ 分析沙箱：独立进程、白名单操作
                  └─ 图表规格生成
                      └─ SQLite 元数据 + Parquet 数据 + Redis 限流
```

## 2. 关键目录

| 路径 | 职责 |
|---|---|
| `app/api/routes/` | 认证、数据集、分析、会话、账户、健康/指标 |
| `app/api/middleware.py` | 纯 ASGI 请求 ID、访问日志、延迟指标、安全响应头 |
| `app/core/` | 设置、JWT/bcrypt、统一错误、Redis 限流、日志、Prometheus |
| `app/models/` | SQLAlchemy 模型 |
| `app/services/dataset_parser.py` | CSV/Excel 读取、列规范化、类型推断、schema |
| `app/services/dataset_service.py` | 后台解析/重解析、受管路径、文件清理 |
| `app/services/intent_service.py` | 模型意图调用、JSON 提取、Pydantic 校验、列级校验 |
| `app/services/analysis_worker.py` | 独立沙箱进程，只执行白名单计划 |
| `app/services/sandbox_runner.py` | 子进程管理、最小环境、超时、结果校验 |
| `app/services/chart_builder.py` | 柱状/折线/饼图/表格规格 |
| `app/services/analysis_service.py` | 全链路编排、SSE 事件、消息持久化 |
| `app/services/ai_gateway.py` | 唯一模型调用入口、降级、记账、预算 |

## 3. 问答时序

```text
Client
  │ POST /datasets/{id}/chat
  ▼
认证 + 用户级限流 + 归属校验
  │
  ├─ 创建/校验 conversation
  ├─ 读取最近 N 条历史
  ├─ AI 网关 → intent（JSON plan）
  ├─ Pydantic + 数据集 schema 白名单校验
  ├─ 独立子进程执行白名单 Pandas 操作
  ├─ 结果行列/数值/规模校验
  ├─ 图表规格生成
  ├─ AI 网关 → conclusion（仅基于计算结果）
  └─ 事务写入 user/assistant 消息
  ▼
{chart_spec, result_table, conclusion, conversation_id, message_id}
```

SSE 版本使用相同编排，依次发送 `status`、`plan`、`result`、`status`、`final` 事件；错误以 `error` 事件返回。SSE 是分析阶段进度流，不是模型 token 流。

## 4. 结构化分析计划

`AnalysisPlan` 只允许：

- 聚合：`sum`、`mean`、`min`、`max`、`count`、`count_distinct`
- 维度：最多 2 个输出维度
- 过滤：等于、不等于、比较、in/not_in、contains、between、空值
- 时间粒度：日、周、月、季度、年
- 排序、最多 1000 行、图表类型

模型输出经过两层约束：Pydantic 字段/范围约束和针对当前数据集列名/类型的白名单校验。沙箱进程再次构造 `AnalysisPlan`，不接收或执行任意代码。

## 5. AI 网关

- `OpenAICompatibleProvider`：`base_url + /chat/completions`，超时、HTTP 错误分类。
- `LocalRuleProvider`：仅开发/测试，确定性地处理常见聚合、分组、趋势和相对日期，并为结论生成基于结果行的摘要。
- 非生产环境远程失败后自动降级到本地提供方；生产环境不启用本地降级。
- 每次网关调用写入 `ai_usage`：操作、提供方、模型、token、估算成本、延迟、成功/失败。
- 调用前检查用户当月累计成本与预算；成功后记录成本；失败也记录审计行。

## 6. 数据与状态

- SQLite：用户、数据集元数据、会话、消息、AI 用量。
- `DATA_DIR/datasets/{user_id}/{uuid}/data.parquet`：标准化数据本体。
- `DATA_DIR/tmp/`：上传临时文件，解析后删除。
- Redis：固定窗口用户级限流键。
- JWT 无服务端会话，故不需要 Redis 会话存储；登出由客户端丢弃 token，短有效期降低风险。

## 7. 扩展方向

- 元数据迁移 PostgreSQL，数据本体迁移对象存储。
- 将 FastAPI BackgroundTasks 换成独立任务队列，支持重试与进度查询。
- 使用 DuckDB/列式引擎处理更大数据量。
- 多实例部署时统一 Redis、数据库、对象存储和指标系统。
