# TutorLoop-AI Backend

FastAPI 后端，提供多 Key 路由池 AI 网关、SSE 流式聊天、视频/图片/PDF 上传与多模态 RAG、
Neo4j 知识图谱构建、BKT 掌握度引擎与自适应路径推荐，以及 JWT 认证、课程/学习房间管理
等完整能力（Phase 1-3 功能已全部完成）。

## 快速开始

1. 复制环境变量示例并填写真实 API Key：

```bash
cp env.example .env
# 编辑 .env，将 LLM_API_KEYS 替换为你的真实 key
```

2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 启动服务：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 测试

```bash
# 安装开发依赖
pip install -r requirements-dev.txt

# 运行单元测试
pytest -q

# 运行测试并收集覆盖率（与 CI 一致）
pytest --cov=app --cov-report=term-missing -q
```

## Docker 运行

```bash
docker build -t tutorloop-ai-backend .
docker run -p 8000:8000 --env-file .env tutorloop-ai-backend
```

## 接口示例

- 健康检查：

```bash
curl http://localhost:8000/health
```

- SSE 聊天：

```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "你好"}]}'
```

## 数据库迁移

开发环境默认使用 SQLAlchemy `create_all()` 自动建表。生产环境建议通过 Alembic 管理：

```bash
alembic upgrade head
```

或在启动时设置 `RUN_ALEMBIC_MIGRATIONS=true` 自动执行。

## 异步任务队列

视频处理与知识图谱抽取会占用大量 CPU/GPU 与 IO，建议通过 ARQ + Redis 在后台执行。

启动 worker：

```bash
arq app.tasks.worker.WorkerSettings
```

若未配置 `REDIS_URL`，上传接口会回退到同步处理。

## 配置说明

| 变量 | 说明 |
| --- | --- |
| `LLM_API_KEYS` | 多个 API Key，逗号分隔 |
| `LLM_BASE_URLS` | 对应 base URL，逗号分隔 |
| `LLM_MODELS` | 对应模型名，逗号分隔 |
| `LOCAL_BASE_URL` | 本地兜底模型服务地址 |
| `LOCAL_MODEL` | 本地兜底模型名 |
| `APP_HOST` / `APP_PORT` | 服务监听地址与端口 |
| `DATABASE_URL` | PostgreSQL 连接串 |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | Neo4j 连接信息 |
| `REDIS_URL` | Redis 连接串（用于 ARQ 任务队列） |
| `RUN_ALEMBIC_MIGRATIONS` | 启动时是否执行 Alembic 迁移 |
| `RECOMMEND_STRATEGY` | 推荐策略：`mastery_gap` 或 `balanced` |

## 学习房间 API

老师可为课程创建学习房间，学生通过短房间号进入并观看课程视频、与 AI 辅导对话。

主要端点：

- `POST /api/courses/{course_id}/rooms` — 创建房间
- `GET /api/courses/{course_id}/rooms` — 列出课程的所有房间
- `GET /api/rooms/{slug}` — 公开房间信息
- `POST /api/rooms/{slug}/join` — 进入房间（校验密码、更新访问统计）
- `PATCH /api/rooms/{room_id}` — 更新房间配置
- `DELETE /api/rooms/{room_id}` — 删除房间

房间支持以下特性：

- 8 位短房间号（URL-safe）
- 可选房间密码
- 可选过期时间
- 允许/禁止匿名访问
- 访问次数 `entry_count` 与最后活动时间 `last_activity_at` 统计
- 自定义配置字段 `config_json`、欢迎语 `welcome_message`、人数上限 `max_participants`

示例：创建公开匿名房间

```bash
curl -X POST "http://localhost:8000/api/courses/$COURSE_ID/rooms" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "初一1班晚自习", "allow_anonymous": true}'
```
