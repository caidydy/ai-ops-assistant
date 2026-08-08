# ai-ops-assistant

智能 OnCall 运维助手：融合 RAG 知识库问答与 AIOps 自动故障诊断的企业级智能运维系统。

系统面向运维场景，以 LangGraph 构建 Agent 编排层，通过 MCP（Model Context Protocol）协议接入日志检索与监控指标工具，在收到告警后自动执行"告警获取 → 日志取证 → 指标分析 → 根因定位 → 修复建议"的完整诊断链路，并将结果以结构化报告输出。

## 核心特性

- **RAG 知识库问答** — 支持 Markdown/纯文本文档上传，自动完成分块、Embedding、向量化入库；对话时基于 Milvus 检索增强生成，回答可溯源至知识文档
- **AIOps 自动故障诊断** — 基于 Plan-Execute-Replan 模式编排诊断流程：规划器制定诊断计划、执行器调用工具取证、重规划器动态调整策略，最终生成包含根因分析与修复建议的结构化诊断报告
- **流式交互** — 对话与诊断过程均通过 SSE 流式输出（工具调用状态、检索结果、内容片段实时推送），前端可呈现完整推理过程
- **MCP 工具集成** — 内置日志查询/告警/监控指标工具服务（本地 Mock 开箱即用），可平滑切换至腾讯云 CLS 真实日志服务
- **Web 控制台** — 原生实现的现代化 Web 界面，无需构建步骤，支持会话管理、流式渲染与 Markdown 展示

## 技术栈

| 类别 | 技术选型 |
|---|---|
| 框架 | FastAPI + LangChain + LangGraph |
| LLM | 阿里云 DashScope 通义千问|
| 向量数据库 | Milvus |
| 工具协议 | MCP（Model Context Protocol） |

## 快速开始

### 环境要求

| 依赖 | 版本/说明 |
|---|---|
| 操作系统 | Windows 10/11（部署脚本基于 Windows 批处理实现） |
| Python | 3.11 ~ 3.13|
| Docker Desktop | 用于运行 Milvus 向量数据库，需提前启动 |
| DashScope API Key | 阿里云百炼平台申请 |

### 部署步骤

```powershell
# 1. 克隆项目
git clone https://github.com/caidydy/ai-ops-assistant.git
cd ai-ops-assistant

# 2. 初始化环境变量（填写 DASHSCOPE_API_KEY）
copy .env.example .env
notepad .env

# 3. 一键启动（自动完成：虚拟环境创建与依赖安装 → Milvus 启动 → MCP 服务启动 → 主服务启动 → 知识文档入库）
.\start-windows.bat
```

启动完成后访问：

- Web 控制台：<http://localhost:9900>
- API 文档（Swagger）：<http://localhost:9900/docs>

停止服务：执行 `.\stop-windows.bat`（同时停止 Milvus 容器）。

## API 接口

| 功能 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 快速对话 | POST | `/api/chat` | 一次性返回回答 |
| 流式对话 | POST | `/api/chat_stream` | SSE 流式输出（工具调用/检索/内容/完成事件） |
| 清空会话 | POST | `/api/chat/clear` | 按会话 ID 清空历史（参数 `sessionId`） |
| 会话查询 | GET | `/api/chat/session/{session_id}` | 获取会话历史 |
| AIOps 诊断 | POST | `/api/aiops` | SSE 流式故障诊断（status/plan/step/report/complete 事件） |
| 文件上传 | POST | `/api/upload` | 上传文档并自动建立向量索引（支持 txt/md，≤10MB） |
| 目录索引 | POST | `/api/index_directory` | 批量索引指定目录下所有文档（参数 `directory_path`） |
| 健康检查 | GET | `/health` | 服务状态与 Milvus 连接状态 |

### 调用示例

```bash
# 快速对话（请求字段为 Id / Question）
curl -X POST "http://localhost:9900/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"Id":"session-123","Question":"服务响应缓慢如何排查？"}'

# AIOps 故障诊断（SSE 流式）
curl -X POST "http://localhost:9900/api/aiops" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"session-123"}' \
  --no-buffer

# 文档上传
curl -X POST "http://localhost:9900/api/upload" \
  -F "file=@aiops-docs/service_unavailable.md"

# 健康检查
curl http://localhost:9900/health
```

SSE 事件格式详见 `app/api/chat.py` 与 `app/api/aiops.py` 中的接口文档注释。

## 项目结构

```
ai-ops-assistant/
├── app/                                # 后端主程序
│   ├── main.py                         # FastAPI 应用入口（路由注册、静态资源挂载）
│   ├── config.py                       # 配置管理（Pydantic Settings，读取 .env）
│   ├── api/                            # API 路由层
│   │   ├── chat.py                     # 对话接口（快速/流式/会话管理）
│   │   ├── aiops.py                    # AIOps 诊断接口（SSE 流式）
│   │   ├── file.py                     # 文档上传与目录索引
│   │   └── health.py                   # 健康检查
│   ├── services/                       # 业务服务层（RAG Agent、AIOps 编排、向量服务）
│   ├── agent/                          # Agent 核心（MCP 客户端、AIOps 规划/执行/重规划）
│   ├── models/                         # Pydantic 数据模型
│   ├── tools/                          # Agent 工具集（知识检索/指标告警/时间）
│   ├── core/                           # 基础设施（LLM 工厂、Milvus 客户端）
│   └── utils/                          # 日志配置
├── static/                             # Web 前端（原生 HTML/JS/CSS，见 static/README.md）
├── mcp_servers/                        # MCP 工具服务（CLS 日志 mock + Monitor 指标 mock，见 mcp_servers/README.md）
├── aiops-docs/                         # 运维知识库语料（RAG 数据源，见 aiops-docs/README.md）
├── scripts/                            # 辅助验证脚本（见 scripts/README.md）
├── .env.example                        # 环境变量模板（复制为 .env 使用）
├── start-windows.bat                   # Windows 一键启动脚本
├── stop-windows.bat                    # Windows 停止脚本
├── vector-database.yml                 # Milvus Docker Compose 配置
├── pyproject.toml                      # 项目元数据与依赖声明
└── uv.lock                             # uv 依赖锁定文件
```

## 配置说明

所有配置通过根目录 `.env` 注入（模板见 `.env.example`），关键项：

| 配置项 | 必填 | 说明 |
|---|---|---|
| `DASHSCOPE_API_KEY` | 是 | 阿里云 DashScope API 密钥 |
| `DASHSCOPE_MODEL` | 否 | 对话模型，默认 `qwen-max` |
| `DASHSCOPE_EMBEDDING_MODEL` | 否 | Embedding 模型，默认 `text-embedding-v4` |
| `MILVUS_HOST` / `MILVUS_PORT` | 否 | Milvus 连接地址，默认 `localhost:19530` |
| `RAG_TOP_K` | 否 | 检索召回条数，默认 3 |
| `MCP_CLS_URL` / `MCP_MONITOR_URL` | 否 | MCP 工具服务地址，默认本地 Mock（8383/8384） |

## 常见问题

**Q: 启动报错 "System Python 3.14 is not supported"**
A: 需安装 Python 3.11~3.13 版本后重试。

**Q: 提示 Docker 未运行或 Milvus 连接失败**
A: 确认 Docker Desktop 已启动，执行 `docker compose -f vector-database.yml up -d` 后重试。

**Q: 页面正常打开但对话报错**
A: 检查 `.env` 中 `DASHSCOPE_API_KEY` 是否正确填写，修改后重启服务。

**Q: 如何新增运维知识文档**
A: 将 Markdown 文档放入 `aiops-docs/` 后重启服务自动入库，或调用 `/api/upload` 接口手动上传，详见 `aiops-docs/README.md`。

**Q: 如何接入真实日志服务**
A: 通过 `MCP_CLS_TRANSPORT` / `MCP_CLS_URL` 切换至腾讯云 CLS，配置步骤见 `mcp_servers/README.md`。

## 许可

保留所有权利（All Rights Reserved）。本项目仅供学习与个人使用，未经授权请勿用于商业用途。

作者：[caidydy](https://github.com/caidydy)