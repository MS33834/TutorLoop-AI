# Phase 4 续：详细执行计划表

- **版本**：v1.0.0
- **状态**：Active
- **日期**：2026-07-02
- **前序阶段**：Phase 1-3 已完成 + Phase 4 部分（部署/CI/PWA/安全加固/50+ bug 修复）已完成

> 本文件是 [03_Roadmap_and_Plan.md](./03_Roadmap_and_Plan.md) 中 Phase 4 续的**逐任务展开版**，供开发团队按表执行。每完成一项将 `[ ]` 改为 `[x]`。

---

## 任务 4.1：配置真实 LLM/VLM API Key，Docker 全链路跑通

### 4.1.1 准备 .env 配置模板（产品经理 + 架构师）
- [ ] 确认使用的 LLM 供应商（DeepSeek / Qwen / OpenAI 兼容）
- [ ] 确认使用的 VLM 供应商（Qwen2.5-VL / GPT-4o）
- [ ] 在 `docker-compose.yml` 中填入真实 API Key（不提交到仓库，用环境变量注入）
- [ ] 验证 `LLM_API_KEYS`、`LLM_BASE_URLS`、`LLM_MODELS` 三个字段长度一致
- [ ] 验证 `VLM_MODEL`、`VLM_BASE_URL`、`VLM_API_KEY` 配置正确

### 4.1.2 Docker Compose 全链路启动（运维工程师）
- [ ] `docker compose up -d` 启动所有服务（postgres + neo4j + redis + backend + worker + frontend）
- [ ] 验证 postgres + pgvector 扩展可用：`docker exec -it <pg> psql -U postgres -c "SELECT * FROM pg_extension WHERE extname='vector';"`
- [ ] 验证 neo4j 可连接：`docker exec -it <neo4j> cypher-shell -u neo4j -p password "RETURN 1;"`
- [ ] 验证 redis 可连接：`docker exec -it <redis> redis-cli ping`
- [ ] 验证 backend 健康检查：`curl http://localhost:8000/live` 返回 200
- [ ] 验证 backend 就绪检查：`curl http://localhost:8000/ready` 返回 200
- [ ] 验证 worker 进程启动：`docker logs <worker>` 无错误

### 4.1.3 数据库迁移验证（后端工程师）
- [ ] `docker exec -it <backend> alembic upgrade head` 成功
- [ ] `docker exec -it <backend> alembic current` 显示 head revision
- [ ] 验证所有表已创建：`docker exec -it <pg> psql -U postgres -d tutorloop -c "\dt"`

### 4.1.4 前端可访问验证（前端工程师）
- [ ] `curl http://localhost:5173`（开发模式）或 `http://localhost:80`（Docker）返回 HTML
- [ ] 前端能调用后端 API：浏览器控制台无 CORS 错误
- [ ] 前端 PWA 注册成功：DevTools > Application > Service Workers 显示已激活

---

## 任务 4.2：端到端（E2E）自动化测试

### 4.2.1 编写后端 API 集成测试（后端工程师 + QA）
- [ ] 创建 `backend/tests/test_e2e_flow.py`
- [ ] 测试用例 1：用户注册 → 登录 → 获取 JWT token
  - 使用 `httpx.AsyncClient` + `TestClient`
  - 验证 access_token 和 refresh_token cookie 返回
  - 验证 `/api/auth/me` 返回用户信息
- [ ] 测试用例 2：老师创建课程 → 上传视频 → 上传资料
  - 用 mock 文件（tmp_path 生成测试视频/图片/PDF）
  - 验证 `/api/courses` POST 返回 course_id
  - 验证 `/api/courses/{id}/videos` POST 返回 video_id
  - 验证 `/api/courses/{id}/materials` POST 返回 material_id
- [ ] 测试用例 3：创建知识节点和边 → 验证 Neo4j 同步
  - POST `/api/courses/{id}/nodes` 创建节点
  - POST `/api/courses/{id}/edges` 创建边
  - GET `/api/courses/{id}/graph` 验证返回
- [ ] 测试用例 4：创建房间 → 学生加入房间
  - POST `/api/rooms` 创建房间
  - POST `/api/rooms/{slug}/join` 加入房间
  - 验证 session_token 返回
  - 验证 entry_count 递增
- [ ] 测试用例 5：学生提问 → AI 回答（mock LLM）
  - POST `/api/rooms/{slug}/ask` 发送文字问题
  - 验证 SSE 流式返回
  - 验证掌握度更新
- [ ] 测试用例 6：截图提问（mock VLM）
  - POST 发送截图 + 文字
  - 验证 SSE 流式返回
- [ ] 测试用例 7：掌握度查询 → 推荐下一步
  - GET `/api/users/me/mastery?course_id=xxx`
  - GET `/api/users/me/recommend?course_id=xxx`
  - 验证推荐节点符合前置依赖约束
- [ ] 测试用例 8：学习报告 → 时间轴
  - GET `/api/users/me/report?course_id=xxx`
  - GET `/api/users/me/timeline?course_id=xxx`
  - GET `/api/users/me/question-distribution`
  - 验证返回数据结构完整
- [ ] 测试用例 9：视频进度同步
  - PUT `/api/users/me/videos/{video_id}/progress`
  - GET `/api/users/me/videos/{video_id}/progress`
  - 验证 position_seconds 持久化
- [ ] 测试用例 10：房间离开 → entry_count 递减
  - POST `/api/rooms/{slug}/leave`
  - 验证 entry_count 递减
- [ ] 所有测试使用 mock LLM/VLM（不消耗真实 API 额度）

### 4.2.2 编写前端 E2E 测试骨架（前端工程师 + QA）
- [ ] 安装 Playwright：`npm install -D @playwright/test`
- [ ] 创建 `frontend/e2e/` 目录
- [ ] 测试用例 1：登录流程
  - 访问 `/#/login`
  - 输入用户名密码
  - 验证跳转到首页
- [ ] 测试用例 2：老师创建课程
  - 访问 TeacherDashboard
  - 填写表单创建房间
  - 验证房间列表更新
- [ ] 测试用例 3：学生进入房间
  - 访问 `/#/room/{slug}`
  - 验证视频播放器加载
  - 验证聊天界面可用
- [ ] 测试用例 4：报告页面
  - 访问 `/#/report/{courseId}`
  - 验证雷达图/热力图渲染

---

## 任务 4.3：性能压测与优化

### 4.3.1 SSE 首字延迟压测（运维工程师 + 后端工程师）
- [ ] 编写压测脚本 `backend/tests/perf/test_sse_latency.py`
- [ ] 测试单用户 SSE 首字延迟（目标 < 1s）
- [ ] 测试 10 并发 SSE 首字延迟
- [ ] 测试 50 并发 SSE 首字延迟
- [ ] 记录 P50/P95/P99 延迟数据
- [ ] 如果不达标，分析瓶颈（DB 查询？LLM API？网关选 key？）

### 4.3.2 并发用户压测（运维工程师）
- [ ] 使用 `locust` 或 `wrk` 进行 HTTP 压测
- [ ] 测试 `/api/rooms/{slug}/join` 并发（目标 50 并发不降级）
- [ ] 测试 `/api/users/me/mastery` 并发查询
- [ ] 测试 `/api/courses` 并发列表查询
- [ ] 监控数据库连接池使用率（目标 < 80%）
- [ ] 监控内存使用（目标 < 512MB per container）

### 4.3.3 数据库慢查询排查（后端工程师）
- [ ] 启用 PostgreSQL 慢查询日志（`log_min_duration_statement = 100`）
- [ ] 执行所有 API 端点，收集慢查询
- [ ] 为慢查询添加索引
- [ ] 验证 N+1 查询（特别是 mastery 查询和 recommendation）
- [ ] 使用 `EXPLAIN ANALYZE` 验证查询计划

### 4.3.4 前端首屏加载优化（前端工程师）
- [ ] 分析构建产物大小（`npm run build` 后的 dist/ 大小）
- [ ] 验证路由懒加载（所有视图组件已懒加载）
- [ ] 添加 `preload` 关键资源（字体、主要 CSS）
- [ ] 添加 `dns-prefetch` / `preconnect` 到 API 域名
- [ ] 压缩图片资源（如果有的话）
- [ ] 验证 Lighthouse Performance 分数（目标 > 80）

---

## 任务 4.4：小规模真实教学场景测试准备

### 4.4.1 准备测试课程内容（产品经理）
- [ ] 选择 3 个学科（如：数学/物理/编程）
- [ ] 每个学科准备 1-2 个教学视频（5-15 分钟）
- [ ] 准备配套 PDF 参考资料
- [ ] 定义知识点范围与掌握度阈值
- [ ] 在系统中创建测试课程并构建知识图谱

### 4.4.2 招募测试学生（产品经理）
- [ ] 招募 10-20 名测试学生
- [ ] 准备测试指南文档（如何进入房间、如何提问、如何查看报告）
- [ ] 准备反馈收集表（Google Form / 问卷星）
- [ ] 安排测试时间窗口

### 4.4.3 反馈收集与迭代（产品经理 + 全团队）
- [ ] 收集学生反馈
- [ ] 分类反馈（UI/UX / 功能缺失 / Bug / 性能）
- [ ] 优先级排序
- [ ] 迭代修复

---

## 任务 4.5：移动端真机兼容性测试

### 4.5.1 iOS Safari 测试（前端工程师 + QA）
- [ ] PWA 安装到主屏幕
- [ ] 视频播放（播放/暂停/拖动/全屏）
- [ ] 截图提问功能
- [ ] SSE 打字机效果
- [ ] 雷达图渲染
- [ ] 横竖屏切换
- [ ] 前后台切换后恢复

### 4.5.2 Android Chrome 测试（前端工程师 + QA）
- [ ] 同 iOS 测试项
- [ ] PWA 安装
- [ ] 通知权限（如果启用）

### 4.5.3 微信内置浏览器专项适配（前端工程师）
- [ ] 视频播放（微信内置播放器可能拦截）
- [ ] 截图功能（微信可能限制 canvas 截图）
- [ ] SSE 兼容性（微信可能不支持 EventSource，需要降级为 fetch stream）
- [ ] 分享链接在微信中打开
- [ ] 二维码识别

---

## 任务 4.6：成本压测与优化

### 4.6.1 统计 API 调用成本（运维工程师 + AI 算法工程师）
- [ ] 模拟一个完整学习会话（观看视频 → 3 次提问 → 1 次截图提问 → 查看报告）
- [ ] 统计 LLM token 消耗
- [ ] 统计 VLM token 消耗
- [ ] 计算单次会话成本
- [ ] 推算月度成本

### 4.6.2 热点答案缓存（后端工程师）
- [ ] 设计缓存 key（course_id + question_hash + screenshot_hash）
- [ ] 在 chat 路由中先查 Redis 缓存
- [ ] 缓存命中时直接返回（非流式，或模拟流式）
- [ ] 缓存未命中时正常调用 LLM，完成后写入缓存
- [ ] 设置缓存 TTL（如 24h）
- [ ] 添加缓存命中率指标

### 4.6.3 模型分层路由（AI 算法工程师 + 后端工程师）
- [ ] 实现问题复杂度判断（基于问题长度、关键词）
- [ ] 简单问题路由到小模型（如 deepseek-chat / qwen-turbo）
- [ ] 复杂问题路由到大模型（如 deepseek-reasoner / qwen-max）
- [ ] 截图问题路由到 VLM
- [ ] 验证分层路由不影响回答质量

---

## 多角色审查清单

每个任务完成后，以下角色需逐项审查：

### 架构师审查
- [ ] 代码是否符合整体架构设计
- [ ] 是否引入了不必要的依赖
- [ ] 接口设计是否与 PRD/TechSpec 一致
- [ ] 是否有安全风险

### 产品经理审查
- [ ] 功能是否满足 PRD 需求
- [ ] 用户体验是否符合预期
- [ ] 边界条件是否考虑

### 后端工程师审查
- [ ] 代码是否有逻辑错误
- [ ] 异常处理是否完整
- [ ] 数据库操作是否高效
- [ ] 是否有并发问题

### 前端工程师审查
- [ ] 前后端接口字段是否匹配
- [ ] 是否有类型不一致
- [ ] 移动端适配是否到位
- [ ] 错误处理是否用户友好

### QA 审查
- [ ] 测试覆盖是否充分
- [ ] 边界条件是否有测试
- [ ] 是否有回归风险

### 运维工程师审查
- [ ] 部署配置是否正确
- [ ] 环境变量是否齐全
- [ ] 监控指标是否覆盖
- [ ] 日志是否可追溯

---

## 验收检查表（交付前必过）

- [ ] `cd backend && pytest -q` → 0 failed
- [ ] `cd frontend && npm run test` → 0 failed
- [ ] `cd frontend && npm run build` → 通过
- [ ] `alembic upgrade head` → 成功（CI 验证）
- [ ] `docker compose up -d` → 所有服务健康
- [ ] CI 全绿（3 个 job: backend / migrations / frontend）
- [ ] 远程仓库无未合并 PR / 未处理 Issue
- [ ] 双仓库同步（GitHub + GitCode）
- [ ] 路线图进度已更新
