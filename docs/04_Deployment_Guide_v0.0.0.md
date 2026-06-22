# TutorLoop-AI 部署与运维指南

- **版本**：v0.0.0
- **状态**：Draft
- **日期**：2026-06-21

---

## 1. 环境变量

### 后端

复制 `backend/env.example` 为 `backend/.env` 并填写：

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL + asyncpg 连接串 |
| `NEO4J_URI` | Neo4j Bolt 地址 |
| `NEO4J_USER` / `NEO4J_PASSWORD` | Neo4j 认证 |
| `LLM_API_KEYS` / `LLM_BASE_URLS` / `LLM_MODELS` | 云端 LLM 多 Key 配置，逗号分隔 |
| `LOCAL_BASE_URL` / `LOCAL_MODEL` | 本地兜底模型 |
| `SENTRY_DSN` | 错误追踪（可选） |

### 前端

| 变量 | 说明 |
| --- | --- |
| `VITE_API_BASE_URL` | 后端 API 地址 |
| `VITE_SENTRY_DSN` | 前端 Sentry（可选） |

---

## 2. 本地一键启动

Docker Compose 启动前，先复制根目录环境变量示例并填写：

```bash
cp env.example .env
# 编辑 .env，至少修改 SECRET_KEY、LLM_API_KEYS 等必填项
docker compose up --build
```

访问：
- 后端：http://localhost:8000
- Neo4j Browser：http://localhost:7474

---

## 3. 前端部署

### Vercel

1. 导入 `frontend` 目录。
2. 在 Dashboard 设置环境变量 `VITE_API_BASE_URL`。
3. 自动构建并发布。

### Cloudflare Pages

1. 使用 Wrangler：`npx wrangler pages deploy frontend/dist`
2. 或在 Pages 构建配置中选择 `frontend` 目录，构建命令 `npm run build`，输出目录 `dist`。

---

## 4. 后端部署

### Render

1. 创建 Blueprint，选择 `backend/render.yaml`。
2. 在环境变量中填写 `LLM_API_KEYS`、`NEO4J_URI`、`SENTRY_DSN` 等。
3. Render 会自动创建 PostgreSQL 并绑定 `DATABASE_URL`。

### Fly.io

```bash
cd backend
fly launch --dockerfile Dockerfile --name tutorloop-backend --region hkg
fly secrets set DATABASE_URL=... NEO4J_URI=... SENTRY_DSN=...
fly deploy
```

### Sealos / 其他 K8s

```bash
cd backend
kubectl apply -f sealos-deployment.yaml
kubectl create secret generic tutorloop-secrets \
  --from-literal=DATABASE_URL=... \
  --from-literal=NEO4J_URI=... \
  --from-literal=SENTRY_DSN=...
```

---

## 5. 监控

- 健康检查：`GET /ready`（存活检查：`GET /live`）
- Sentry：配置 `SENTRY_DSN` 后自动上报后端异常与前端错误。
- 负载测试：`python tests/load_test.py --base-url https://your-api.com`

---

## 6. 成本优化检查清单

- [ ] 关闭未使用的云端 Key，保留本地兜底可用。
- [ ] 多模态请求压缩截图分辨率 ≤ 720p。
- [ ] 开启 RAG 向量检索缓存（同视频帧去重）。
- [ ] 为 Render/Fly 设置自动休眠（Render sleep / Fly auto_stop_machines）。
- [ ] 非生产环境使用 `LOCAL_BASE_URL` 替代云端模型。
- [ ] 定期清理 `uploads/` 与过期截图。

---

## 7. 小规模测试方案

1. 招募 10-20 名学生，覆盖至少 2 门课程。
2. 每个学生完成「观看视频 → 提问 3-5 次 → 提交反馈 → 查看报告」流程。
3. 收集指标：首字延迟、回答满意度、推荐点击率、掌握度变化趋势。
4. 收集 5 份以上可用性反馈，输出改进清单。
