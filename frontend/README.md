# TutorLoop-AI 前端

基于 Vue 3 + Vite + Pinia 的 PWA 自适应学习平台。

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

# 运行单元测试
npm run test
```

## 环境变量

开发前请复制 `env.production.example` 为 `.env.local` 并按需修改：

```bash
cp env.production.example .env.local
```

| 变量名 | 默认值 | 说明 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://localhost:8000` | 后端 API 基础地址 |
| `VITE_SENTRY_DSN` | （空） | Sentry 错误追踪 DSN，留空则不加载 Sentry SDK |

## 功能

Phase 1-3 功能已全部完成：

- 移动端优先的聊天界面，SSE 流式接收后端回答并展示打字机效果
- JWT 认证（登录/注册/刷新令牌），access token 内存存储 + refresh cookie
- 视频上传与播放，支持截图提问、时间戳捕获与多模态 RAG
- 课程与学习房间管理（老师创建房间、学生凭短房间号进入）
- 知识图谱可视化（Cytoscape）展示与编辑
- BKT 掌握度雷达图实时展示
- 自适应路径推荐「下一步学习」
- 学习报告与班级学情报告
- PWA 完整配置（manifest 图标、iOS meta 标签、Service Worker 自动更新、API/媒体运行时缓存）
