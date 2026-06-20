# TutorLoop-AI 技术方案文档

- **版本**：v0.0.0
- **状态**：Draft
- **日期**：2026-06-20
- **负责人**：Tech Lead / TutorLoop-AI 团队

---

## 变更日志

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v0.0.0 | 2026-06-20 | 初始版本，定义技术栈、架构、数据模型与算法 |

---

## 1. 技术栈总览

| 层级 | 选型 |
| --- | --- |
| 前端框架 | Vue 3 + Vite + Pinia + VueUse |
| PWA | Workbox（离线缓存、Service Worker） |
| UI 组件 | Element Plus / Ant Design Vue（移动端优先） |
| 后端框架 | Python 3.11 + FastAPI + Uvicorn |
| AI 编排 | LangGraph + LangChain |
| 文本大模型 | DeepSeek-V3 / Qwen-Max / GPT-4o-mini |
| 多模态模型 | Qwen2.5-VL / GPT-4o / Gemini 1.5 Flash |
| 本地兜底 | vLLM / Ollama + Qwen3.5-4B / Qwen2.5-VL |
| 图数据库 | Neo4j Community / Neo4j Aura |
| 关系 / 向量数据库 | Supabase PostgreSQL + pgvector |
| 对象存储 | Cloudflare R2 / AWS S3 |
| 部署 | Docker + Sealos / Render / Fly.io |
| 监控 | Sentry + Prometheus / Grafana（可选） |

---

## 2. 系统架构

```
┌─────────────────────────────────────┐
│  老师端 / 学生端 PWA (Vue3 + Workbox)  │
└──────────────────┬──────────────────┘
                   │
        ┌──────────▼──────────┐
        │  CDN (Vercel/Pages) │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │ FastAPI AI Gateway  │
        └──────────┬──────────┘
                   │
    ┌──────────────┼──────────────┐
    │              │              │
┌───▼────┐   ┌────▼─────┐   ┌────▼─────┐
│多Key池 │   │LangGraph │   │ 数据存储  │
│路由   │   │Agent编排 │   │         │
└───┬────┘   └────┬─────┘   └───┬──────┘
    │             │             │
┌───▼────┐   ┌────▼─────┐   ┌───▼──────┐
│云端LLM │   │多模态RAG │   │ Neo4j   │
│/VLM   │   │苏格拉底  │   │ PostgreSQL│
└────────┘   │BKT/推荐  │   │ 对象存储  │
             └──────────┘   └──────────┘
```

---

## 3. AI Gateway 详细设计

### 3.1 多 Key 健康池

维护每个 API Key 的元数据：

```json
{
  "provider": "deepseek",
  "model": "deepseek-chat",
  "key": "sk-***",
  "remaining_quota": 10000,
  "error_rate": 0.02,
  "avg_rtt_ms": 450,
  "status": "healthy"
}
```

- **心跳探测**：每 30s 发送轻量探测请求。
- **状态机**：`healthy` / `degraded` / `offline`。
- **自动恢复**：degraded Key 在错误率下降后恢复为 healthy。

### 3.2 路由策略

1. 按请求类型选择模型：
   - 纯文本问答 → 文本模型。
   - 含截图 / 视频帧 → 多模态模型。
2. 同模型下选择健康 Key。
3. 加权轮询，权重 = 剩余额度 / RTT。
4. 单次请求失败重试最多 2 次，连续失败标记 degraded。

### 3.3 降级兜底

- 云端调用超过 3s 未返回首 token → 切换本地模型。
- 全部云端 Key 不可用 → 仅使用本地模型。
- 本地模型不可用时 → 返回友好提示并记录告警。

### 3.4 SSE 流式转发

- 后端使用 FastAPI `StreamingResponse` 异步迭代。
- 前端使用 `EventSource` 接收 token 流。
- 目标首字延迟 < 1s。

---

## 4. LangGraph Agent 工作流

```
[老师上传资料]
    │
    ▼
┌─────────────────────┐
│ 知识图谱构建 Agent   │  视频切帧 / ASR / OCR → 抽取知识点实体与依赖 → 写入 Neo4j
└─────────────────────┘
    │
    ▼
[学生提问]
    │
    ▼
┌─────────────────────┐
│ 多模态 RAG Agent     │  视频帧向量检索 + 图谱节点召回 + 参考资料拼接
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ 苏格拉底教学 Agent   │  根据掌握度生成引导式回答
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ 掌握度追踪引擎 BKT   │  根据回答与行为信号更新节点概率
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ 自适应路径规划 Agent  │  拓扑依赖 + 掌握度 → 推荐下一个最优先学习节点
└─────────────────────┘
```

---

## 5. 数据存储与模型

### 5.1 PostgreSQL 核心表

```sql
-- 用户表
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role VARCHAR(20) NOT NULL, -- teacher / student
    name VARCHAR(100),
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 课程表
CREATE TABLE courses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    video_url TEXT,
    created_by UUID REFERENCES users(id),
    config_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 学习房间表
CREATE TABLE rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID REFERENCES courses(id),
    slug VARCHAR(32) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    expires_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'active'
);

-- 知识点节点表（与 Neo4j 同步）
CREATE TABLE knowledge_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID REFERENCES courses(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    threshold FLOAT DEFAULT 0.8,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 掌握度表
CREATE TABLE mastery (
    user_id UUID REFERENCES users(id),
    node_id UUID REFERENCES knowledge_nodes(id),
    p_known FLOAT DEFAULT 0.3,
    p_t FLOAT DEFAULT 0.3,
    interactions_count INT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, node_id)
);

-- 学习交互记录表
CREATE TABLE interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    room_id UUID REFERENCES rooms(id),
    course_id UUID REFERENCES courses(id),
    video_timestamp FLOAT,
    screenshot_url TEXT,
    question_text TEXT,
    answer_text TEXT,
    is_correct BOOLEAN,
    help_count INT DEFAULT 0,
    watch_seconds FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.2 Neo4j 图模型

```cypher
(:KnowledgeNode {
  id: string,
  course_id: string,
  name: string,
  threshold: float,
  description: string
})-[:PREREQUISITE]->(:KnowledgeNode)
```

### 5.3 向量存储

- 使用 Supabase `pgvector` 扩展。
- 存储视频帧向量、文本片段向量。
- 检索时结合 metadata（时间戳、课程 ID）过滤。

---

## 6. 核心算法

### 6.1 知识图谱构建

1. 视频切片：按固定间隔或场景切换切帧。
2. ASR / OCR 提取文本。
3. 多模态模型理解画面与文本内容。
4. 结构化 Prompt 输出知识点与依赖：

```json
{
  "nodes": [
    {"id": "n1", "name": "一元一次方程", "description": "..."}
  ],
  "edges": [
    {"from": "n1", "to": "n2", "relation": "prerequisite"}
  ]
}
```

5. 人工校验后写入 Neo4j。

### 6.2 BKT 掌握度追踪

四参数定义：

- `P(L0)`：初始掌握概率，默认 0.3。
- `P(T)`：学习概率，默认 0.3。
- `P(G)`：猜测概率，默认 0.2。
- `P(S)`：失误概率，默认 0.1。

观测到正确回答：

```
P(L_t | correct) = (P(L_t) * (1 - P(S))) /
                   (P(L_t) * (1 - P(S)) + (1 - P(L_t)) * P(G))
```

观测到错误回答：

```
P(L_t | wrong) = (P(L_t) * P(S)) /
                 (P(L_t) * P(S) + (1 - P(L_t)) * (1 - P(G)))
```

学习转移更新：

```
P(L_{t+1}) = P(L_t | obs) + (1 - P(L_t | obs)) * P(T)
```

### 6.3 自适应路径规划

```
candidate_nodes = {
  n ∈ nodes | not_mastered(n) ∧ ∀p ∈ prereq(n), mastered(p)
}

recommend_node = argmin_{n ∈ candidate_nodes} cost(n)

cost(n) = α * remaining_video_seconds(n)
        + β * prereq_depth(n)
        + γ * (1 - historical_error_rate(n))
```

---

## 7. API 设计

| Method | Path | 说明 |
| --- | --- | --- |
| POST | /api/auth/login | 登录获取 JWT |
| POST | /api/courses | 创建课程 |
| POST | /api/courses/:id/rooms | 创建学习房间 |
| GET | /api/rooms/:slug | 获取房间信息 |
| GET | /api/rooms/:slug/graph | 获取知识图谱 |
| POST | /api/rooms/:slug/ask | SSE 流式提问 |
| POST | /api/interactions | 上报学习行为 |
| GET | /api/users/:id/mastery | 获取掌握度数据 |
| GET | /api/users/:id/recommend | 获取下一步推荐 |
| GET | /api/users/:id/report | 获取学习报告 |

---

## 8. 部署架构

| 组件 | 部署方式 |
| --- | --- |
| 前端 | Vercel / Cloudflare Pages，自动 CI/CD |
| 后端 | Docker 镜像，部署于 Sealos / Render / Fly.io |
| 关系数据库 | Supabase 托管 PostgreSQL |
| 图数据库 | Neo4j Aura 免费版或自建容器 |
| 对象存储 | Cloudflare R2 |
| 本地模型 | LM Studio / vLLM / Ollama（测试与兜底） |

---

## 9. 安全与合规

- **认证**：JWT + Refresh Token，Token 过期自动刷新。
- **授权**：老师只能管理自己的课程与房间；学生只能访问被授权的房间。
- **数据最小化**：仅收集学习必需的行为数据与截图。
- **隐私保护**：截图 7 天后自动清理；敏感字段加密存储。
- **传输安全**：全站 HTTPS，SSE 同样走 TLS。
