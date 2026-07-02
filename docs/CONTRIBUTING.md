# TutorLoop-AI 开发者文档

- **版本**：v1.0.0
- **日期**：2026-07-02
- **适用范围**：所有参与 TutorLoop-AI 开发的团队成员

---

## 1. 仓库信息

| 仓库 | 地址 | 用途 |
| --- | --- | --- |
| GitHub | `MS33834/tutorloop-ai` | 主仓库，CI/CD 触发 |
| GitCode | `badhope/tutorloop-ai` | 镜像仓库，国内访问 |

**双仓库同步规则**：每次提交后必须同时推送到两个仓库：
```bash
git push origin main    # GitHub
git push gitcode main   # GitCode
```

---

## 2. 每次开发前必做检查清单

**这是强制规范，每次开始开发工作前必须逐项执行：**

### 2.1 检查远程仓库状态
```bash
# 拉取最新代码
git fetch origin && git fetch gitcode

# 检查本地是否落后远程
git log --oneline HEAD..origin/main    # 有输出说明远程有新提交
git log --oneline HEAD..gitcode/main   # 同上

# 检查是否有未推送的本地提交
git log --oneline origin/main..HEAD

# 检查工作区状态
git status -sb
```

### 2.2 检查 GitHub PR 和 Issue
- 访问 https://github.com/MS33834/tutorloop-ai/pulls 检查是否有未合并的 PR
- 访问 https://github.com/MS33834/tutorloop-ai/issues 检查是否有未处理的 Issue
- 或使用 API：
  ```bash
  curl -s -H "Authorization: token <TOKEN>" "https://api.github.com/repos/MS33834/tutorloop-ai/pulls?state=open" | python -m json.tool
  curl -s -H "Authorization: token <TOKEN>" "https://api.github.com/repos/MS33834/tutorloop-ai/issues?state=open" | python -m json.tool
  ```

### 2.3 检查分支状态
```bash
# 检查是否有除 main 外的其他分支
git branch -a -v
# 或通过 API
curl -s -H "Authorization: token <TOKEN>" "https://api.github.com/repos/MS33834/tutorloop-ai/branches" | python -m json.tool
```

### 2.4 检查 CI 是否全绿
- 访问 https://github.com/MS33834/tutorloop-ai/actions 检查最新 CI 运行状态
- 或使用 API：
  ```bash
  curl -s -H "Authorization: token <TOKEN>" "https://api.github.com/repos/MS33834/tutorloop-ai/actions/runs?per_page=5" | python -c "
  import sys, json
  data = json.load(sys.stdin)
  for r in data.get('workflow_runs', []):
      print(f'{r[\"name\"]} | {r[\"conclusion\"] or r[\"status\"]} | {r[\"head_commit\"][\"message\"][:60]}')
  "
  ```
- **如果 CI 不是全绿，必须先修复 CI 问题再开始新开发**

### 2.5 检查测试是否通过
```bash
cd backend && python -m pytest tests/ -q
cd frontend && npm run test
cd frontend && npm run build
```

---

## 3. 每次开发后必做检查清单

**完成开发后，提交前必须逐项执行：**

### 3.1 本地验证
- [ ] 后端测试全部通过：`cd backend && pytest -q`
- [ ] 前端测试全部通过：`cd frontend && npm run test`
- [ ] 前端构建成功：`cd frontend && npm run build`
- [ ] 无密钥/敏感信息泄露：`grep -r "ghp_\|sk-\|password.*=" --include="*.py" --include="*.js" --include="*.yml" .`（确保无真实密钥）

### 3.2 提交规范
```bash
# 查看变更
git status
git diff --stat

# 添加变更（按文件添加，不要用 git add -A 如果有敏感文件）
git add <specific-files>

# 提交（使用规范化 commit message）
git commit -m "type: 简短描述

详细说明（可选）
"
```

**Commit 类型**：
- `feat`: 新功能
- `fix`: Bug 修复
- `refactor`: 重构
- `test`: 测试
- `docs`: 文档
- `chore`: 构建/配置
- `perf`: 性能优化

### 3.3 推送并验证 CI
```bash
# 推送到双仓库
git push origin main
git push gitcode main

# 等待 CI 触发后检查状态（约 1-2 分钟）
# 访问 https://github.com/MS33834/tutorloop-ai/actions
# 确保所有 job 都是绿色
```

### 3.4 推送后远程仓库健康检查（强制）

> ⚠️ **每次完成开发并推送后，必须逐项执行以下检查。这是团队强制规范，不得跳过。**
> 目的：及时发现社区反馈（PR/Issue）、异常分支、CI 回归，避免问题累积。

```bash
# TOKEN 替换为有效的 GitHub Personal Access Token（不要写入仓库）
TOKEN=<your-github-token>
REPO=MS33834/tutorloop-ai
```

- [ ] **3.4.1 CI 是否全绿**（最关键）
  ```bash
  curl -s -H "Authorization: token $TOKEN" \
    "https://api.github.com/repos/$REPO/actions/runs?per_page=3" | \
    python3 -c "import sys,json; [print(r['head_sha'][:7],'|',r['name'],'|',r['conclusion']) for r in json.load(sys.stdin)['workflow_runs']]"
  ```
  - 预期：最新一次 run 的三个 job（backend / migrations / frontend）conclusion 均为 `success`
  - **若非全绿，必须立即定位失败 job 并修复，不得开始下一个任务**

- [ ] **3.4.2 是否有未处理的 Pull Request**
  ```bash
  curl -s -H "Authorization: token $TOKEN" \
    "https://api.github.com/repos/$REPO/pulls?state=open" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(f'开放 PR 数: {len(d)}'); [print(' #',p['number'],p['title']) for p in d]"
  ```
  - 预期：`开放 PR 数: 0`（或已知 PR 已 review）
  - **若有新 PR，必须 review 并决定合并/关闭/要求修改**

- [ ] **3.4.3 是否有未处理的 Issue**
  ```bash
  curl -s -H "Authorization: token $TOKEN" \
    "https://api.github.com/repos/$REPO/issues?state=open" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(f'开放 Issue 数: {len(d)}'); [print(' #',i['number'],i['title']) for i in d]"
  ```
  - 预期：`开放 Issue 数: 0`（或已知 Issue 已排期）
  - **若有新 Issue，必须评估优先级并回应**

- [ ] **3.4.4 是否有待合并/异常分支**
  ```bash
  curl -s -H "Authorization: token $TOKEN" \
    "https://api.github.com/repos/$REPO/branches" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print('分支:'); [print(' ',b['name'],b['commit']['sha'][:7]) for b in d]"
  ```
  - 预期：仅 `main` 分支
  - **若有其他分支，确认是否需要合并到 main 或删除**

- [ ] **3.4.5 双仓库是否同步**（GitHub = GitCode）
  ```bash
  git fetch origin && git fetch gitcode
  git log --oneline origin/main -1
  git log --oneline gitcode/main -1
  ```
  - 预期：两个 remote 的 HEAD commit SHA 一致
  - **若不一致，重新推送到落后的仓库**

- [ ] **3.4.6 记录检查结果**
  - 在本次任务的交付说明/commit message/计划表中简要记录检查结果
  - 示例：「远程检查：CI 全绿 ✓ / PR 0 / Issue 0 / 仅 main 分支 / 双仓库同步」

### 3.5 更新路线图进度
- 打开 `docs/03_Roadmap_and_Plan.md` 和 `docs/06_Phase4_Detailed_Plan.md`
- 将完成的任务项 `[ ]` 改为 `[x]`
- 提交进度更新：
  ```bash
  git add docs/03_Roadmap_and_Plan.md docs/06_Phase4_Detailed_Plan.md
  git commit -m "docs: 更新路线图进度"
  git push origin main && git push gitcode main
  ```

---

## 4. 项目结构

```
tutorloop-ai/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── routers/         # API 路由 (auth, chat, courses, rooms, users)
│   │   ├── services/        # 业务逻辑 (bkt_engine, rag_service, ...)
│   │   ├── models/db.py     # SQLAlchemy 数据模型
│   │   ├── schemas.py       # Pydantic 请求/响应模型
│   │   ├── config.py        # 环境变量配置
│   │   ├── gateway.py       # AI 网关 (多 Key 池)
│   │   ├── main.py          # FastAPI 应用入口
│   │   └── tasks/           # ARQ 异步任务
│   ├── alembic/             # 数据库迁移
│   ├── tests/               # 测试
│   ├── requirements.txt     # Python 依赖
│   └── Dockerfile
├── frontend/                # Vue 3 PWA 前端
│   ├── src/
│   │   ├── views/           # 页面组件
│   │   ├── components/      # UI 组件
│   │   ├── stores/          # Pinia 状态管理
│   │   ├── api/             # API 封装
│   │   └── router/          # 路由
│   ├── package.json
│   └── Dockerfile
├── docs/                    # 项目文档
├── .github/workflows/ci.yml # CI 配置
├── docker-compose.yml       # 本地开发编排
└── env.example              # 环境变量模板
```

---

## 5. 开发环境搭建

### 5.1 后端
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 配置环境变量
cp env.example .env
# 编辑 .env 填入真实配置

# 数据库迁移
alembic upgrade head

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5.2 前端
```bash
cd frontend
npm ci
npm run dev    # 开发服务器 http://localhost:5173
```

### 5.3 Docker 全栈
```bash
cp env.example .env  # 编辑填入配置
docker compose up -d
```

---

## 6. 关键开发注意事项

### 6.1 安全规范
- **永远不要**将 API Key、密码、JWT Secret 提交到代码仓库
- **永远不要**在代码中硬编码密钥，使用环境变量
- 使用 `grep -r "ghp_\|sk-\|password" .` 在提交前检查
- `.env` 文件已在 `.gitignore` 中，不要移除

### 6.2 数据库迁移规范
- 每次修改 `models/db.py` 后，创建新的 alembic 迁移：`alembic revision --autogenerate -m "描述"`
- **不要**修改已提交的迁移文件（除非是初始迁移的 bug 修复）
- 迁移文件命名：`<revision_id>_<snake_case_description>.py`
- 确保迁移链连续：`down_revision` 正确指向前一个

### 6.3 前端规范
- 使用 Vue 3 Composition API (`<script setup>`)
- 路由使用 `createWebHashHistory`（hash 路由，兼容静态托管）
- API 调用统一通过 `src/api/client.js` 的 `apiFetch`
- 分享链接必须包含 `#`：`${origin}/#/room/${slug}`

### 6.4 后端规范
- 所有 API 端点必须有 `@router` 装饰器和类型注解
- 异步操作使用 `async/await`
- 数据库操作使用 `AsyncSessionLocal`
- LLM 调用通过 `gateway` 模块，不要直接调用模型 API

---

## 7. 故障排查

### CI 失败
1. 查看 https://github.com/MS33834/tutorloop-ai/actions 找到失败的 job
2. 点击进入查看详细日志
3. 常见问题：
   - **migrations job 失败**：检查迁移文件是否使用了 `op.run_sync`（不存在），改用 `op.get_bind()` + `Base.metadata.create_all(bind)`；若报 `column already exists` / `relation already exists`，说明初始迁移用 `create_all` 已创建完整 schema，后续 `ADD COLUMN`/`CREATE TABLE` 迁移与之冲突——项目未上线时应 squash 为单一初始迁移（删除冗余迁移文件）
   - **backend job 失败**：检查测试是否通过、依赖是否完整
   - **frontend job 失败**：检查 `npm run test` 和 `npm run build`

### 本地测试失败
1. 确保所有依赖已安装：`pip install -r requirements.txt -r requirements-dev.txt`
2. 确保环境变量已设置：`SECRET_KEY` 至少 32 字符
3. 清理缓存：`pip cache purge` / `rm -rf .pytest_cache`

### Docker 启动失败
1. 检查端口冲突：`lsof -i :8000` / `lsof -i :5432`
2. 检查环境变量：`docker compose config` 查看解析后的配置
3. 查看日志：`docker compose logs <service-name>`

---

## 8. 团队角色与职责

| 角色 | 职责 | 每次任务必做 |
| --- | --- | --- |
| 架构师 | 架构设计、技术选型、代码审查 | 审查架构一致性、安全性 |
| 产品经理 | PRD 需求、验收标准、用户反馈 | 审查功能完整性、用户体验 |
| 后端工程师 | API 开发、数据库、服务层 | 审查逻辑正确性、异常处理 |
| 前端工程师 | UI 组件、页面、PWA | 审查接口匹配、移动端适配 |
| AI 算法工程师 | RAG、BKT、推荐算法 | 审查算法正确性、效果 |
| 运维工程师 | 部署、CI/CD、监控 | 审查部署配置、监控覆盖 |
| QA | 测试、回归、兼容性 | 审查测试覆盖、边界条件 |

**每个任务必须经过所有相关角色审查后才能交付。**
