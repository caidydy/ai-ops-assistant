# static — 网页前端

无构建步骤的纯静态前端，由 FastAPI 直接提供。启动服务后访问 `http://localhost:9900` 即是本页面。

| 文件 | 作用 |
|---|---|
| `index.html` | 页面骨架（会话列表 + 对话区 + AIOps 入口） |
| `styles.css` | 样式 |
| `app.js` | 逻辑：会话管理、SSE 流式接收、Markdown 渲染 |

依赖两个 CDN 库（marked、highlight.js），内网/离线部署时需要改成本地引用。前后端接口约定以 `app/api/` 下的 docstring 为准。