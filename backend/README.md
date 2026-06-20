# TutorLoop-AI Backend

Phase 1 最小可用的 FastAPI AI Gateway，包含多 Key 路由池、SSE 流式聊天接口与健康检查。

## 快速开始

1. 复制环境变量示例并填写真实 API Key：

```bash
cp .env.example .env
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

## 配置说明

| 变量 | 说明 |
| --- | --- |
| `LLM_API_KEYS` | 多个 API Key，逗号分隔 |
| `LLM_BASE_URLS` | 对应 base URL，逗号分隔 |
| `LLM_MODELS` | 对应模型名，逗号分隔 |
| `LOCAL_BASE_URL` | 本地兜底模型服务地址 |
| `LOCAL_MODEL` | 本地兜底模型名 |
| `APP_HOST` / `APP_PORT` | 服务监听地址与端口 |
