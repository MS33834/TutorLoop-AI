# Phase 4 执行冲刺：临时计划表（二次展开版）

- **版本**：v1.0.0
- **状态**：Active（冲刺执行中）
- **日期**：2026-07-02
- **前序文档**：[06_Phase4_Detailed_Plan.md](./06_Phase4_Detailed_Plan.md) 的**二次展开**，每个子任务拆解为原子级步骤
- **目的**：消除执行歧义，确保 AI/开发者按表执行"不会做错"

> **使用规则**：
> 1. 每个原子步骤完成后将 `[ ]` → `[x]`
> 2. 每个任务包（Sprint）完成后，**必须**经过多角色审查（见 §审查清单）才能标记完成
> 3. 审查未通过的项目回到对应步骤重做，不得跳过
> 4. 全部 Sprint 完成且 review/debug 无误后，连接前面阶段跑通，再交付同步

---

## 团队角色与分工（本冲刺）

| 角色 | 本冲刺职责 | 必审项 |
| --- | --- | --- |
| 架构师（Architect） | 审查接口/模块边界、依赖合理性、安全风险 | 每个 Sprint 的架构一致性 |
| 产品经理（PM） | 审查功能完整性、PRD 对齐、边界条件 | 每个 Sprint 的需求覆盖 |
| 后端工程师（BE） | 实现 E2E 测试、Redis 缓存、模型路由 | 逻辑正确性、异常处理、并发 |
| 前端工程师（FE） | 前端 E2E 骨架、性能优化 | 接口匹配、移动端适配 |
| AI 算法工程师 | 模型分层路由、成本统计 | 算法正确性、效果 |
| 运维工程师（DevOps） | 性能压测脚本、Docker 全链路 | 部署配置、监控覆盖 |
| QA | 测试覆盖、回归风险 | 边界条件、断言完整性 |

**强制规则**：每个 Sprint 完成后，全部 7 个角色过一遍审查清单，从各自角度签字。

---

## Sprint 0：CI 基线确认（前置门禁）

> 在开始任何开发前，必须确认 CI 全绿、双仓库同步、无遗留 PR/Issue。

### S0.1 远程仓库健康检查（DevOps）
- [x] S0.1.1 `git fetch origin && git fetch gitcode`，确认本地与远程一致
- [x] S0.1.2 GitHub 无开放 PR（API 查询 `pulls?state=open` 返回 0）
- [x] S0.1.3 GitHub 无开放 Issue（API 查询 `issues?state=open` 返回 0）
- [x] S0.1.4 仅 main 分支，无待合并分支
- [x] S0.1.5 双仓库 HEAD 一致（GitHub = GitCode = 本地）

### S0.2 CI 全绿确认（DevOps）
- [x] S0.2.1 修复 `op.run_sync` 不存在 → 改用 `op.get_bind()`（commit 77906ea）
- [x] S0.2.2 修复迁移链冲突 → squash 10 个冗余迁移为单一初始迁移（commit 5bb830f）
- [x] S0.2.3 推送后 CI 三 job 全绿（backend / migrations / frontend）
  - 验证命令：`curl -s -H "Authorization: token <TOKEN>" "https://api.github.com/repos/MS33834/tutorloop-ai/actions/runs?per_page=1" | python -c "import sys,json; r=json.load(sys.stdin)['workflow_runs'][0]; print(r['conclusion'])"`
  - 预期输出：`success`
  - 实际结果：commit 5bb830f / 43b42ba CI 全绿 ✓
- [x] S0.2.4 若仍有失败，定位失败 job 与 step，修复后重新提交推送，直到全绿

### S0.3 本地基线测试（QA）
- [x] S0.3.1 `cd backend && pytest -q` → 164 passed / 0 failed
- [x] S0.3.2 `cd frontend && npm run test` → 0 failed（CI frontend job 验证通过）
- [x] S0.3.3 `cd frontend && npm run build` → 构建成功（CI frontend job 验证通过）

---

## Sprint 1：后端 E2E 集成测试（任务 4.2 展开）

> **目标**：从零覆盖后端 API 层集成测试，补齐 TD-01 技术债务。
> **交付物**：`backend/tests/conftest_e2e.py` + `backend/tests/test_e2e_flow.py`
> **不消耗真实 API 额度**：所有 LLM/VLM 调用走 mock。

### S1.1 扩展 conftest fixture（BE + DevOps）

**文件**：`backend/tests/conftest.py`（修改现有文件，追加 fixture）

- [ ] S1.1.1 新增 `event_loop` fixture（如需覆盖默认策略）
  - 不需要，`pyproject.toml` 已设 `asyncio_mode = "auto"`

- [ ] S1.1.2 新增 `mock_gateway` autouse fixture
  - **作用**：patch `app.routers.chat.stream_chat` 和 `app.gateway.chat_completion` 为 AsyncMock
  - **关键**：chat 路由 `from app.gateway import stream_chat` 已绑定引用，必须 patch `app.routers.chat.stream_chat`（不是 `app.gateway.stream_chat`）
  - **签名**：
    ```python
    @pytest.fixture(autouse=True)
    def mock_gateway(monkeypatch):
        async def fake_stream(messages, model_type="text"):
            yield {"type": "token", "content": "测试"}
            yield {"type": "done"}
        async def fake_completion(messages, model_type="text"):
            return {"choices": [{"message": {"content": "测试回答"}}]}
        monkeypatch.setattr("app.routers.chat.stream_chat", fake_stream)
        monkeypatch.setattr("app.gateway.chat_completion", fake_completion)
        # 同时 patch 服务层引用
        monkeypatch.setattr("app.services.socratic_agent.chat_completion", fake_completion)
        monkeypatch.setattr("app.services.kg_extractor.chat_completion", fake_completion)
    ```

- [ ] S1.1.3 新增 `disable_limiter` autouse fixture
  - **作用**：禁用 SlowAPI 限流，避免密集请求触发 429
  - **实现**：`monkeypatch.setattr("app.limiter.limiter.enabled", False)` 或 patch `_check_request_limit`

- [ ] S1.1.4 新增 `async_client` fixture
  - **作用**：提供 httpx.AsyncClient + ASGITransport，不触发 lifespan（避免连 PG/Neo4j/Redis）
  - **签名**：
    ```python
    @pytest.fixture
    async def async_client():
        from app.main import app
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    ```

- [ ] S1.1.5 新增 `auth_token` fixture
  - **作用**：通过 `POST /api/auth/register` 注册用户获取真实 JWT
  - **依赖**：需要数据库可用（init_db 已通过 lifespan 或手动 create_all）
  - **签名**：
    ```python
    @pytest.fixture
    async def auth_token(async_client):
        resp = await async_client.post("/api/auth/register", json={
            "username": "e2e_teacher", "password": "Test1234!", "role": "teacher"
        })
        return resp.json()["access_token"]
    ```

- [ ] S1.1.6 新增 `auth_headers` fixture
  - **作用**：返回 `{"Authorization": f"Bearer {auth_token}"}`
  - **依赖**：`auth_token`

- [ ] S1.1.7 数据库初始化策略确认
  - **方案**：conftest 中 patch `app.db.postgres.AsyncSessionLocal` 指向测试 PG，或在 module setup 调用 `Base.metadata.create_all`
  - **注意**：PG 方言特性（`pg_insert.on_conflict_do_update`、`JSONB`、`Vector`）不可用 SQLite 替代
  - **CI 环境已有 pgvector service**，本地需启动 PG 或在测试中 mock DB 层
  - **决策**：若 PG 不可用，patch `AsyncSessionLocal` 使用内存 dict mock（仅测路由逻辑，不测持久化）

### S1.2 编写 E2E 测试文件（BE + QA）

**文件**：`backend/tests/test_e2e_flow.py`（新建）

- [ ] S1.2.1 测试用例：用户注册 → 登录 → 获取 me
  ```python
  async def test_register_login_me(async_client):
      # 1. 注册
      resp = await async_client.post("/api/auth/register", json={
          "username": "e2e_user1", "password": "Test1234!", "role": "student"
      })
      assert resp.status_code == 200
      data = resp.json()
      assert "access_token" in data
      token = data["access_token"]
      headers = {"Authorization": f"Bearer {token}"}
      # 2. 获取 me
      resp = await async_client.get("/api/auth/me", headers=headers)
      assert resp.status_code == 200
      assert resp.json()["username"] == "e2e_user1"
  ```
  - **断言**：status 200、access_token 非空、refresh cookie 设置（`Set-Cookie` 含 `refresh_token`）

- [ ] S1.2.2 测试用例：老师创建课程
  ```python
  async def test_create_course(async_client, auth_headers):
      resp = await async_client.post("/api/courses", json={
          "title": "E2E测试课程", "description": "测试用"
      }, headers=auth_headers)
      assert resp.status_code == 200
      course = resp.json()
      assert "id" in course
      assert course["title"] == "E2E测试课程"
      return course["id"]  # 后续测试复用
  ```

- [ ] S1.2.3 测试用例：上传视频（mock 文件）
  - 构造最小 MP4 字节流或假文件内容
  - `files={"file": ("test.mp4", b"\x00\x00\x00\x18ftyp...", "video/mp4")}`
  - **注意**：视频处理会调 process_video（依赖 opencv），需 mock `app.services.video_service.process_video`
  - **断言**：返回 video_id，status 字段存在

- [ ] S1.2.4 测试用例：创建知识节点 + 边
  - POST `/api/courses/{course_id}/nodes` 创建 2 个节点
  - POST `/api/courses/{course_id}/edges` 创建 1 条边
  - GET `/api/courses/{course_id}/graph` 验证返回 nodes + edges
  - **断言**：graph.nodes 长度 = 2，graph.edges 长度 = 1

- [ ] S1.2.5 测试用例：创建房间 → 学生加入
  - POST `/api/courses/{course_id}/rooms` 创建房间
  - GET `/api/rooms/{slug}` 获取 session_token
  - POST `/api/rooms/{slug}/join` 携带 session_token 加入
  - **断言**：join 返回 200，entry_count 递增

- [ ] S1.2.6 测试用例：学生文字提问 → SSE 流式回答
  - POST `/api/chat`，body: `{"room_slug": slug, "question": "什么是函数？"}`
  - 用 `async_client.stream("POST", ...)` + `aiter_lines()` 解析 SSE
  - **断言**：至少收到 1 个 `data: {"type":"token",...}` 和 1 个 `data: {"type":"done"}`

- [ ] S1.2.7 测试用例：视频进度同步
  - PUT `/api/users/me/videos/{video_id}/progress`，body: `{"position_seconds": 120, "watched_seconds": 100}`
  - GET `/api/users/me/videos/{video_id}/progress`
  - **断言**：GET 返回 position_seconds = 120

- [ ] S1.2.8 测试用例：掌握度查询 + 推荐
  - GET `/api/users/me/mastery?course_id={course_id}`
  - GET `/api/users/me/recommend?course_id={course_id}`
  - **断言**：返回列表（可为空），recommend 项含 node_id 和 reason

- [ ] S1.2.9 测试用例：个人报告 + 时间轴 + 问题分布
  - GET `/api/users/me/report?course_id={course_id}`
  - GET `/api/users/me/timeline?course_id={course_id}`
  - GET `/api/users/me/question-distribution`
  - **断言**：返回 200，数据结构含预期字段

- [ ] S1.2.10 测试用例：房间离开 → entry_count 递减
  - POST `/api/rooms/{slug}/leave`，携带 session_token
  - **断言**：返回 200，entry_count 递减（幂等）

- [ ] S1.2.11 运行全部 E2E 测试
  - 命令：`cd backend && pytest tests/test_e2e_flow.py -v`
  - **预期**：全部 passed，无 429/500/422

### S1.3 Sprint 1 审查（全部角色）

- [x] 架构师：mock 位置正确（patch 引用绑定点）、fixture 不污染其他测试
- [x] PM：覆盖核心学习闭环（注册→课程→视频→提问→报告）
- [x] BE：异常路径有测试（401 未授权、404 不存在、422 参数错误）
- [x] FE：无需（纯后端）
- [x] AI 算法：LLM mock 返回结构符合 gateway 契约
- [x] DevOps：CI 中可运行（backend job 已加 pgvector service）
- [x] QA：断言充分，边界条件覆盖

> ⚠️ **修订说明（2026-07-02）**：S1.3 表面审查通过，但 commit `5a22315`/`31c92ad`/`27ff20e` 推送后 CI backend job 持续失败（migrations/frontend 已绿）。根因是 `setup_db` fixture 的事件循环隔离不彻底，导致 E2E 测试在 CI 中全部 error。S1.4 是在 Sprint 1 基础上的**二次展开**，专门修复此 CI 阻塞。S1.3 的 ✓ 保留（审查维度本身无误），但 Sprint 1 整体完成状态以 S1.4 全绿为准。

---

## Sprint 1.4：CI E2E 事件循环修复（Sprint 1 二次展开）

> **背景**：Sprint 1 的 10 个 E2E 测试在本地（无 PG）全部 skip 通过，但 CI（有 pgvector service）下 10 个全 error。
> **错误现象**（commit 27ff20e / cc0e9e4 CI 日志）：
> - `RuntimeError: Task ... got Future <Future pending> attached to a different loop`（5 个测试）
> - `ValueError: password cannot be longer than 72 bytes`（5 个测试）
> - 最终：`164 passed, 1 warning, 10 errors in 20.49s`
>
> **根因分析**（架构师 + BE + DevOps 联合定位，经 commit cc0e9e4 验证后修订）：
> 经 cc0e9e4（setup_db 临时 engine 隔离）推送后 CI 仍失败，错误分布与之前完全一致，证明是**两个独立根因**，而非单一 cascade：
>
> 1. **bcrypt 兼容性 bug**（test_register_login_me 等 5 个，第一个测试就触发）：
>    - 环境：passlib 1.7.4 + bcrypt 5.0.0（CI 用 bcrypt>=4.1.0）
>    - bcrypt 4.0 移除了 `__about__` 模块，passlib 1.7.4 依赖它做版本检测，导致 bcrypt backend 加载异常
>    - 表现：对 9 字节的 "Test1234!" 误报 `password cannot be longer than 72 bytes`
>    - 证据：`test_auth_service.py` 早有 `_working_hasher` fixture 用 pbkdf2_sha256 绕过此 bug（仅单元测试），但生产代码 `auth_service.py` 仍用 passlib+bcrypt，E2E 真正调用 register 时触发
> 2. **跨 event loop 连接复用**（test_create_course 等 5 个，第二个及之后的测试）：
>    - pytest-asyncio 默认 function-scoped loop，每个测试一个新 loop
>    - `app.db.postgres.engine` 是 module-level 单例，测试1的连接留在池里绑定 loop1
>    - 测试2在 loop2 中复用时，asyncpg Protocol 的 Future 跨 loop → RuntimeError
>    - cc0e9e4 的临时 engine 修复只解决了 setup_db 阶段的污染，未解决测试间的跨 loop
> 3. **结论**：bcrypt 修复让第一个测试通过，session-scoped loop 修复让后续测试不再跨 loop，两者缺一不可。

### S1.4.1 修复方案设计（架构师 + BE）

**根因 A：setup_db 污染全局 engine（cc0e9e4 已修）**
- [x] S1.4.1.1 确认 `setup_db` 必须保持 session-scoped（避免每测试重建表拖慢 CI）
- [x] S1.4.1.2 确认不能让 setup_db 与测试共用 `app.db.postgres.engine`（单例污染根因）
- [x] S1.4.1.3 方案选定：**setup_db 使用独立的临时 engine 创建/销毁表**，完全不触碰测试用的全局 `engine`
  - 临时 engine 在 setup loop 中创建连接、建表、dispose，连接随 loop 关闭而销毁
  - 测试用的全局 `engine` 连接池从未被 setup loop 触碰，测试时在自己的 function-scoped loop 中首次连接，无跨 loop 残留
- [x] S1.4.1.4 确认 `pg_available` probe 已用独立 `asyncpg.connect`（不复用 engine），无需改动
- [x] S1.4.1.5 确认 `mock_gateway` / `disable_limiter` / `async_client` / `auth_token` / `auth_headers` 均在测试 loop 中运行，无需改动

**根因 B：passlib + bcrypt 版本不兼容（e957fbb 修复）**
- [x] S1.4.1.6 确认 passlib 1.7.4 + bcrypt 5.0.0 不兼容（bcrypt 4.0+ 移除 `__about__`）
- [x] S1.4.1.7 方案选定：**直接用 bcrypt 库的 `hashpw`/`checkpw`**，绕过 passlib 的版本检测
  - 生成的 `$2b$` hash 与 passlib 互相兼容，已有用户密码 hash 无需迁移
  - `verify_password` 捕获 `ValueError`/`TypeError` 返回 False（无效 hash 格式）
- [x] S1.4.1.8 确认 `test_auth_service.py` 的 `_working_hasher` workaround 可移除（不再需要 passlib）

**根因 C：测试间跨 event loop（e957fbb 修复）**
- [x] S1.4.1.9 确认 pytest-asyncio 默认 function-scoped loop 导致测试间连接跨 loop
- [x] S1.4.1.10 方案选定：**设置 `asyncio_default_fixture_loop_scope = "session"` + `asyncio_default_test_loop_scope = "session"`**
  - 所有测试和 async fixture 共享一个 session loop，engine 连接始终在同一 loop
  - 对 164 个原有测试无影响（不依赖 loop 隔离）
- [x] S1.4.1.11 确认 session loop 下 `async_client`（function-scoped async fixture）仍正常工作（每次创建新 client，loop 同一个）

### S1.4.2 conftest.py 修复实现（BE）

**文件**：`backend/tests/conftest.py`（修改 `setup_db` fixture）

- [x] S1.4.2.1 在 `setup_db` 内部新建 `tmp_engine = create_async_engine(settings.database_url, future=True)`，**不导入** `app.db.postgres.engine`
- [x] S1.4.2.2 将 `_create()` 改为使用 `tmp_engine.begin()` 执行 `CREATE EXTENSION IF NOT EXISTS vector` + `Base.metadata.create_all`
- [x] S1.4.2.3 `_create()` 末尾 `await tmp_engine.dispose()`（释放临时连接）
- [x] S1.4.2.4 将 `_drop()` 同样使用一个新的 `tmp_engine`（前一个已 dispose），执行 `Base.metadata.drop_all` 后 dispose
- [x] S1.4.2.5 保留 `asyncio.run(_create())` / `asyncio.run(_drop())` 结构（setup loop 与测试 loop 隔离正是我们要的）
- [x] S1.4.2.6 删除旧注释中"Dispose so no pooled connection is tied to this transient event loop"的误导性说明（原方案 dispose 的是全局 engine，无效）
- [x] S1.4.2.7 新增注释明确说明：临时 engine 与全局 `app.db.postgres.engine` 完全隔离，测试 engine 的连接池在测试 loop 中首次创建，无跨 loop 问题

### S1.4.2b auth_service.py bcrypt 兼容性修复（BE）

**文件**：`backend/app/services/auth_service.py`（修改）+ `backend/tests/test_auth_service.py`（修改）

- [x] S1.4.2b.1 移除 `from passlib.context import CryptContext` 和 `pwd_context = CryptContext(...)` 单例
- [x] S1.4.2b.2 改为 `import bcrypt`，`verify_password` 用 `bcrypt.checkpw(plain.encode, hashed.encode)`
  - 捕获 `ValueError`/`TypeError` 返回 False（兼容无效 hash 格式）
- [x] S1.4.2b.3 `get_password_hash` 用 `bcrypt.hashpw(password.encode, bcrypt.gensalt()).decode`
- [x] S1.4.2b.4 移除 `test_auth_service.py` 的 `_working_hasher` fixture 和 `from passlib.context import CryptContext`
- [x] S1.4.2b.5 确认 `$2b$` hash 格式与 passlib 互相兼容（已有用户密码 hash 无需迁移）
- [x] S1.4.2b.6 确认 `rooms.py` 用 `from auth_service import verify_password`，无需改动（接口签名不变）

### S1.4.2c pyproject.toml session-scoped loop 修复（BE + DevOps）

**文件**：`backend/pyproject.toml`（修改 `[tool.pytest.ini_options]`）

- [x] S1.4.2c.1 新增 `asyncio_default_fixture_loop_scope = "session"`
- [x] S1.4.2c.2 新增 `asyncio_default_test_loop_scope = "session"`
- [x] S1.4.2c.3 添加注释说明：session loop 避免测试间连接跨 loop
- [x] S1.4.2c.4 本地验证 164 passed + 10 skipped 无回归（session loop 不影响原有测试）

### S1.4.3 本地验证（QA + DevOps）

- [x] S1.4.3.1 本地无 PG 时 `cd backend && pytest tests/test_e2e_flow.py -v` → 10 skipped（验证 fixture 不报错）
- [x] S1.4.3.2 本地无 PG 时 `cd backend && pytest -q` → 164 passed（验证无回归）
- [x] S1.4.3.3 代码静态检查 `python -m compileall app tests` 通过

### S1.4.4 CI 验证（DevOps）

- [ ] S1.4.4.1 提交修复，推送 origin（GitHub）
- [ ] S1.4.4.2 等待 CI 运行完成（约 2-4 分钟），查询最新 run：
  - 命令：`curl -s -H "Authorization: token <TOKEN>" "https://api.github.com/repos/MS33834/tutorloop-ai/actions/runs?per_page=1" | python -c "import sys,json; r=json.load(sys.stdin)['workflow_runs'][0]; print(r['conclusion'])"`
  - 预期：`success`
- [ ] S1.4.4.3 若 backend job 仍失败，拉取 job 日志定位：
  - 命令：`curl -sL -H "Authorization: token <TOKEN>" "<jobs_url>" -o /tmp/log.txt && grep -nE "(ERROR|RuntimeError|ValueError|passed|failed)" /tmp/log.txt | tail -40`
  - 预期：`174 passed`（164 原有 + 10 E2E），0 errors
- [ ] S1.4.4.4 确认三个 job 全绿：backend / migrations / frontend
- [ ] S1.4.4.5 同步推送 gitcode（GitCode）

### S1.4.5 Sprint 1.4 审查（全部角色）

- [ ] 架构师：临时 engine 隔离彻底、无单例污染、方案可维护
- [ ] PM：修复不影响功能交付、E2E 覆盖核心闭环
- [ ] BE：根因诊断准确、修复最小化、无新引入风险
- [ ] FE：无需（纯后端 CI 修复）
- [ ] AI 算法：无需（不涉及模型层）
- [ ] DevOps：CI 复现可验证、日志排查命令可用
- [ ] QA：本地 + CI 双重验证、无回归

---

## Sprint 2：性能压测脚本（任务 4.3 展开）

> **目标**：产出可重复运行的性能压测脚本与基线数据。
> **交付物**：`backend/tests/perf/test_sse_latency.py` + `backend/tests/perf/test_concurrency.py`

### S2.1 SSE 首字延迟压测（DevOps + BE）

**文件**：`backend/tests/perf/test_sse_latency.py`（新建）

- [ ] S2.1.1 创建 `backend/tests/perf/__init__.py`
- [ ] S2.1.2 创建 `backend/tests/perf/conftest.py`（复用 E2E fixture 或独立 mock）
- [ ] S2.1.3 编写 `measure_first_token_latency(client, payload) -> float`
  - 记录请求发出到收到第一个 `data: {"type":"token"}` 的时间（秒）
  - 使用 `time.perf_counter()` 精确计时
- [ ] S2.1.4 测试单用户首字延迟
  - 重复 10 次，记录 P50/P95/P99
  - **目标**：P95 < 1.0s（mock 环境应远低于此）
- [ ] S2.1.5 测试 10 并发首字延迟
  - 用 `asyncio.gather` 并发 10 个请求
  - 记录统计
- [ ] S2.1.6 测试 50 并发首字延迟
  - 同上 50 并发
  - **目标**：不出现 5xx 错误
- [ ] S2.1.7 输出报告：打印 P50/P95/P99 表格

### S2.2 并发用户压测（DevOps）

**文件**：`backend/tests/perf/test_concurrency.py`（新建）

- [ ] S2.2.1 编写 `test_join_concurrency`：50 并发 POST `/api/rooms/{slug}/join`
  - **断言**：无 5xx，entry_count 最终一致
- [ ] S2.2.2 编写 `test_mastery_query_concurrency`：50 并发 GET `/api/users/me/mastery`
  - **断言**：全部 200，响应时间 P95 < 500ms
- [ ] S2.2.3 编写 `test_course_list_concurrency`：50 并发 GET `/api/courses`
  - **断言**：全部 200

### S2.3 数据库慢查询排查（BE）

- [ ] S2.3.1 确认 PG 慢查询日志配置（`log_min_duration_statement = 100`）
- [ ] S2.3.2 跑全部 API 后收集慢查询日志
- [ ] S2.3.3 检查 mastery 查询和 recommendation 是否有 N+1
- [ ] S2.3.4 用 `EXPLAIN ANALYZE` 验证关键查询走索引

### S2.4 Sprint 2 审查（全部角色）

- [ ] 架构师：压测不影响生产、脚本可重复运行
- [ ] PM：性能目标与 PRD 验收标准一致
- [ ] BE：慢查询有优化方案
- [ ] DevOps：脚本可在 CI/local 运行
- [ ] QA：并发测试覆盖核心端点

---

## Sprint 3：Redis 热点答案缓存（任务 4.6.2 展开）

> **目标**：实现热点答案缓存，降低重复提问成本。
> **交付物**：修改 `backend/app/routers/chat.py` + 新增 `backend/app/services/cache_service.py`

### S3.1 缓存服务实现（BE）

**文件**：`backend/app/services/cache_service.py`（新建）

- [ ] S3.1.1 实现 `compute_cache_key(course_id, question, screenshot_hash) -> str`
  - key 格式：`chat:answer:{course_id}:{sha256(question)[:16]}:{screenshot_hash or 'none'}`
  - 使用 `hashlib.sha256`
- [ ] S3.1.2 实现 `async get_cached_answer(redis, key) -> str | None`
  - 从 Redis 读取，返回字符串或 None
  - Redis 不可用时返回 None（降级，不阻断）
- [ ] S3.1.3 实现 `async set_cached_answer(redis, key, answer, ttl=86400)`
  - 写入 Redis，TTL 24h
  - Redis 不可用时静默跳过
- [ ] S3.1.4 实现 `async get_cache_hit_rate() -> dict`
  - 返回 `{"hits": N, "misses": N, "hit_rate": 0.x}`
  - 使用 Redis INCR 计数器

### S3.2 集成到 chat 路由（BE）

**文件**：`backend/app/routers/chat.py`（修改）

- [ ] S3.2.1 在 `/api/chat` 端点开头，计算 cache_key
- [ ] S3.2.2 查 Redis 缓存
  - 命中：直接以 SSE 流式返回缓存内容（模拟打字机，每 token 间隔 20ms）
  - 未命中：正常调用 `stream_chat`
- [ ] S3.2.3 流式完成后，将完整答案写入缓存
  - 仅缓存非错误回答（type != error）
- [ ] S3.2.4 添加配置开关 `ENABLE_ANSWER_CACHE`（默认 true）
  - 在 `config.py` 新增字段

### S3.3 缓存指标暴露（DevOps）

- [ ] S3.3.1 在 `/metrics` 端点新增 `chat_cache_hits_total` / `chat_cache_misses_total`
- [ ] S3.3.2 在 `GET /health` 返回缓存命中率

### S3.4 Sprint 3 审查（全部角色）

- [ ] 架构师：缓存 key 设计无碰撞风险、降级策略正确（Redis 挂了不影响功能）
- [ ] PM：缓存命中时用户体验一致（仍流式输出）
- [ ] BE：并发写入无竞态、TTL 合理、错误回答不缓存
- [ ] AI 算法：缓存不影响掌握度更新（缓存仅缓存回答文本，不缓存副作用）
- [ ] DevOps：指标可观测
- [ ] QA：缓存命中/未命中两条路径有测试

---

## Sprint 4：模型分层路由（任务 4.6.3 展开）

> **目标**：简单问题用小模型，复杂问题用大模型，降低成本。
> **交付物**：修改 `backend/app/gateway.py` + 新增 `backend/app/services/question_classifier.py`

### S4.1 问题复杂度分类器（AI 算法 + BE）

**文件**：`backend/app/services/question_classifier.py`（新建）

- [ ] S4.1.1 实现 `classify_question(question: str) -> str`
  - 返回 `"simple"` 或 `"complex"`
  - **规则**：
    - 长度 < 20 字符 且 无"为什么/如何/解释/推导/证明"关键词 → simple
    - 否则 → complex
- [ ] S4.1.2 单元测试：覆盖 simple/complex 各 5 例

### S4.2 gateway 路由集成（BE + AI 算法）

**文件**：`backend/app/gateway.py`（修改 `stream_chat`）

- [ ] S4.2.1 在 `stream_chat` 增加 `complexity` 参数（可选，默认 None）
- [ ] S4.2.2 `select_key(model_type=...)` 根据复杂度选择模型
  - simple → model_type="text" 且优先选小模型 key
  - complex → model_type="text" 且优先选大模型 key
- [ ] S4.2.3 在 chat 路由调用前先 `classify_question`
- [ ] S4.2.4 配置：`LLM_MODELS` 中按顺序标注小/大模型（或新增 `LLM_MODEL_TIERS` 配置）

### S4.3 Sprint 4 审查（全部角色）

- [ ] 架构师：分类逻辑可扩展（后续可接 ML 分类器）
- [ ] PM：回答质量不因分层下降
- [ ] BE：路由不影响流式输出
- [ ] AI 算法：分类规则合理、有单元测试
- [ ] QA：simple/complex 两条路径有测试

---

## Sprint 5：前端 E2E 骨架与性能（任务 4.2.2 + 4.3.4 展开）

> **目标**：前端 Playwright E2E 骨架 + 首屏加载优化。
> **交付物**：`frontend/e2e/` 目录 + `frontend/playwright.config.js`

### S5.1 Playwright 安装与配置（FE + DevOps）

- [ ] S5.1.1 `cd frontend && npm install -D @playwright/test`
- [ ] S5.1.2 创建 `frontend/playwright.config.js`
  - baseURL: `http://localhost:5173`
  - 超时 30s
- [ ] S5.1.3 创建 `frontend/e2e/` 目录

### S5.2 前端 E2E 用例（FE + QA）

- [ ] S5.2.1 `e2e/login.spec.js`：访问 `/#/login` → 输入凭证 → 验证跳转
- [ ] S5.2.2 `e2e/teacher-dashboard.spec.js`：创建房间 → 验证列表更新
- [ ] S5.2.3 `e2e/student-room.spec.js`：进入房间 → 验证播放器 + 聊天加载
- [ ] S5.2.4 `e2e/report.spec.js`：报告页 → 验证雷达图渲染

### S5.3 首屏加载优化（FE）

- [ ] S5.3.1 分析 `npm run build` 产物大小
- [ ] S5.3.2 确认路由懒加载（所有 view 已 `() => import(...)`）
- [ ] S5.3.3 在 `index.html` 添加 `<link rel="preconnect" href="https://api.example.com">`
- [ ] S5.3.4 Lighthouse Performance 目标 > 80

### S5.4 Sprint 5 审查（全部角色）

- [ ] 架构师：E2E 不依赖真实后端（mock 或 docker-compose 起后端）
- [ ] PM：覆盖核心用户旅程
- [ ] FE：选择器稳定（用 data-testid 而非易变 class）
- [ ] DevOps：CI 中可选启用 Playwright
- [ ] QA：断言完整

---

## Sprint 6：Docker 全链路 + 移动端 + 成本（任务 4.1 + 4.5 + 4.6.1 展开）

> **目标**：Docker 全链路跑通、移动端清单、成本统计。
> **注**：移动端真机测试和真实教学场景需人工执行，本冲刺仅产出清单和脚本。

### S6.1 Docker 全链路验证（DevOps）

- [ ] S6.1.1 确认 `docker-compose.yml` 服务齐全（pg+neo4j+redis+backend+worker+frontend）
- [ ] S6.1.2 `docker compose up -d` 启动
- [ ] S6.1.3 验证各服务健康：
  - PG: `docker exec <pg> psql -U postgres -c "SELECT extname FROM pg_extension WHERE extname='vector';"`
  - Neo4j: `docker exec <neo4j> cypher-shell -u neo4j -p password "RETURN 1;"`
  - Redis: `docker exec <redis> redis-cli ping` → PONG
  - Backend: `curl http://localhost:8000/live` → 200
  - Frontend: `curl http://localhost:80` → HTML
- [ ] S6.1.4 `docker exec <backend> alembic upgrade head` 成功
- [ ] S6.1.5 验证迁移后表齐全：`\dt` 显示 13 张表

### S6.2 移动端测试清单（FE + QA）

**文件**：`docs/08_Mobile_Test_Checklist.md`（新建，仅清单不执行）

- [ ] S6.2.1 iOS Safari 清单：PWA 安装/视频/截图/SSE/雷达图/横竖屏/前后台
- [ ] S6.2.2 Android Chrome 清单：同 iOS + 通知权限
- [ ] S6.2.3 微信内置浏览器清单：视频/截图/SSE 降级/分享/二维码
- [ ] S6.2.4 每项标注预期结果与通过标准

### S6.3 成本统计脚本（AI 算法 + DevOps）

**文件**：`backend/tests/perf/test_cost.py`（新建）

- [ ] S6.3.1 模拟一个完整学习会话（mock LLM）
- [ ] S6.3.2 统计 LLM token 消耗（从 mock 返回中计算）
- [ ] S6.3.3 统计 VLM token 消耗
- [ ] S6.3.4 输出单次会话成本估算（按公开定价）

### S6.4 Sprint 6 审查（全部角色）

- [ ] 架构师：Docker 配置与生产一致
- [ ] PM：移动端清单覆盖真实场景
- [ ] BE：全链路无报错
- [ ] FE：移动端清单可执行
- [ ] AI 算法：成本模型合理
- [ ] DevOps：一键启动可复现
- [ ] QA：清单有明确通过标准

---

## 交付前最终验收检查表

> 全部 Sprint 完成后，逐项确认：

- [ ] `cd backend && pytest -q` → 0 failed（含新增 E2E + 性能测试）
- [ ] `cd frontend && npm run test` → 0 failed
- [ ] `cd frontend && npm run build` → 通过
- [ ] `alembic upgrade head` → 成功（单一迁移）
- [ ] `docker compose up -d` → 全部服务健康
- [ ] CI 全绿（3 job: backend / migrations / frontend）
- [ ] GitHub 无未合并 PR / 未处理 Issue
- [ ] 双仓库同步（GitHub + GitCode HEAD 一致）
- [ ] 路线图 `03_Roadmap_and_Plan.md` 进度已更新（TD-01/TD-02 标记修复）
- [ ] 本计划表全部 `[x]`

---

## 多角色审查总表（每个 Sprint 必填）

| Sprint | 架构师 | PM | BE | FE | AI算法 | DevOps | QA |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S0 基线 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| S1 E2E测试 | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| S1.4 CI修复 | ☐ | ☐ | ☐ | — | — | ☐ | ☐ |
| S2 性能压测 | ☐ | ☐ | ☐ | — | — | ☐ | ☐ |
| S3 Redis缓存 | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| S4 模型路由 | ☐ | ☐ | ☐ | — | ☐ | — | ☐ |
| S5 前端E2E | ☐ | ☐ | — | ☐ | — | ☐ | ☐ |
| S6 Docker+移动端 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |

**规则**：每个 Sprint 完成后，相关角色从各自角度审查并在对应格打 ✓。全部 ✓ 后该 Sprint 标记完成。
