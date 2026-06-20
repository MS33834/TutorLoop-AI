# TutorLoop-AI 前端

基于 Vue 3 + Vite + Pinia 的 PWA 聊天界面骨架。

## 快速开始

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览生产构建
npm run preview
```

## 环境变量

开发前请复制 `.env.example` 为 `.env.local` 并按需修改：

```bash
cp .env.example .env.local
```

| 变量名 | 默认值 | 说明 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://localhost:8000` | 后端 API 基础地址 |

## Phase 1 功能

- 移动端优先的聊天界面
- SSE 流式接收后端回答并展示打字机效果
- 占位「截图提问」按钮
- PWA 基础配置（Service Worker 自动更新）
