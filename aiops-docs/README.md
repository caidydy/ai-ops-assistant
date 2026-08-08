# aiops-docs — 运维知识库

存放 AIOps 诊断用的知识文档（Markdown）。服务启动时会自动上传到向量库，故障诊断时 Agent 会检索这些文档作为依据。

## 现有文档

| 文件 | 对应故障 |
|---|---|
| `cpu_high_usage.md` | CPU 使用率过高 |
| `memory_high_usage.md` | 内存使用率过高 |
| `disk_high_usage.md` | 磁盘空间不足 |
| `slow_response.md` | 服务响应缓慢 |
| `service_unavailable.md` | 服务不可用 |

## 添加新知识

1. 在 `aiops-docs/` 放一个 `.md` 文件（建议包含：告警名称、排查步骤、解决方案）
2. 重启 `start-windows.bat`，脚本会自动上传新文档

也可以手动入库：

```powershell
curl -X POST http://localhost:9900/api/upload -F "file=@aiops-docs\新文档.md"
```