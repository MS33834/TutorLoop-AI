# TutorLoop-AI 测试方案

- **版本**：v0.0.0
- **状态**：Draft
- **日期**：2026-06-25

---

## 1. 目标

在每次迭代与发布前，通过自动化测试 + 手动冒烟测试保证：

1. 后端核心服务（认证、聊天、课程、房间、BKT、推荐）行为正确。
2. 前端状态管理、API 客户端、组件渲染无回归。
3. Docker Compose 能完整拉起 PostgreSQL + Neo4j + Redis + Backend + Worker + Frontend。
4. 生产部署配置（Render / Sealos / Fly.io）环境变量完整、密钥安全。

---

## 2. 自动化测试

### 2.1 后端单元测试

```bash
cd backend
python -m pytest -q
```

- 当前基线：**163 passed / 0 failed**。
- 新增功能必须配套测试，PR 不允许降低整体覆盖率。

### 2.2 前端单元/集成测试

```bash
cd frontend
npm run test
```

- 当前基线：**19 passed / 0 failed**。
- 覆盖范围：
  - `stores/user.js`：token 内存存储、JWT 过期判断、refresh 去重、logout。
  - `stores/chat.js`：房间隔离、消息追加、SSE token 拼接、清空。
  - `api/client.js`：GET 去重、5xx 重试、401 刷新重试、错误详情提取。

### 2.3 前端构建与安全审计

```bash
cd frontend
npm run build
npm audit
```

- `npm run build` 必须零错误。
- `npm audit` 必须 **0 vulnerabilities**；发现漏洞后立即升级依赖。

---

## 3. Docker Compose 冒烟测试

在装有 Docker 的环境中执行：

```bash
docker compose up --build -d
```

待所有服务 healthy 后验证：

| 步骤 | 命令/操作 | 预期结果 |
| --- | --- | --- |
| 1 | `curl http://localhost:8000/ready` | `{"ready":true}` |
| 2 | `curl http://localhost:80` | 返回 `index.html` |
| 3 | 浏览器打开 `http://localhost:80` | PWA 登录页加载，无 CSP 报错 |
| 4 | 注册/登录一个账号 | 拿到 access token，刷新 cookie 已设置 |
| 5 | 创建一个课程 | 课程列表返回新课程 |
| 6 | 上传一段测试视频 | 视频进入 processing，worker 处理后状态变 completed |
| 7 | 查看课程知识图谱 | Neo4j 中已有节点/边（需配置真实 VLM） |
| 8 | 进入房间提问 | SSE 流式返回 AI 回答 |
| 9 | 查看掌握度雷达图 | BKT 数据已更新 |
| 10 | 点击“推荐下一步” | 返回符合前置依赖的知识点 |

> 当前沙箱无 Docker 运行时，上述冒烟测试需在本地或 CI 环境补充执行。

---

## 4. 生产部署前检查清单

| 检查项 | 说明 |
| --- | --- |
| `SECRET_KEY` | 长度 ≥ 32，随机生成，web/worker 一致 |
| `LLM_API_KEYS` / `LLM_BASE_URLS` / `LLM_MODELS` | 长度一致，逗号分隔 |
| `VLM_BASE_URL` / `VLM_API_KEY` | 配置真实视觉模型，否则知识图谱为空 |
| `CORS_ORIGINS` | 必须包含生产前端域名 |
| `SENTRY_DSN` | 可选，生产建议开启 |
| uploads 存储 | K8s 多节点场景需 `ReadWriteMany` 或对象存储 |
| 数据库迁移 | 确认 `RUN_ALEMBIC_MIGRATIONS=true` 且 migration 已应用 |

---

## 5. 回归测试触发时机

- 每次 `git push` 前本地执行后端 `pytest` + 前端 `npm run test`。
- 每次依赖升级后执行 `npm audit`。
- 每次修改 `docker-compose.yml`、Dockerfile、K8s YAML 后执行一次 `docker compose up --build`。
- 生产发布前对照第 4 节检查清单逐项确认。
