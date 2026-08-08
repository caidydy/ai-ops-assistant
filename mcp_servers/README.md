# mcp_servers — 日志与监控工具

给 AIOps 诊断提供数据来源的两个工具服务。项目默认使用**本地 mock**（模拟日志、模拟告警、模拟监控指标），零配置，`start-windows.bat` 会自动把它们启动。

| 服务 | 文件 | 端口 | 提供什么 |
|---|---|---|---|
| 日志/告警 | `cls_server.py` | 8383 | 模拟告警列表、日志搜索、告警历史 |
| 监控指标 | `monitor_server.py` | 8384 | CPU、内存、错误率、请求延迟等指标 |

## 默认模式（本地 mock，推荐）

不需要任何配置。主项目 `.env` 里保持：

```ini
MCP_CLS_TRANSPORT=streamable-http
MCP_CLS_URL=http://localhost:8383/mcp
MCP_MONITOR_TRANSPORT=streamable-http
MCP_MONITOR_URL=http://localhost:8384/mcp
```

mock 数据特点：每次诊断都会基于当前时间动态生成告警，日志、指标在同一个时间窗内，Agent 可以完整走完"告警 → 日志 → 指标"的分析链路。

## 可选：接入真实腾讯云 CLS

如果你想用真实云端的日志和告警，按下面三步：

1. 在 `mcp_servers/` 下把 `.env.example` 复制为 `.env`，填入你的腾讯云密钥：

```powershell
copy mcp_servers\.env.example mcp_servers\.env
notepad mcp_servers\.env
```

2. 启动官方 CLS 网关（需要 Node.js）：

```powershell
cd mcp_servers
npx -y cls-mcp-server@latest
```

3. 修改主项目 `.env`，把 CLS 指向真实服务：

```ini
MCP_CLS_TRANSPORT=sse
MCP_CLS_URL=http://localhost:3000/sse
```

改完重启服务。Monitor 仍用本地 mock 即可。

## 自检

改过 mock 服务代码后，可以运行 `scripts\verify_mock_mcp.py` 验证整个工具链路是否正常。