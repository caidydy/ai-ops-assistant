# scripts — 辅助脚本

## verify_mock_mcp.py

一键自检脚本：自动拉起 mock 服务 → 调用工具验证 → 清理退出。修改过 `mcp_servers/` 下的工具后，用它确认链路没坏。

```powershell
python scripts\verify_mock_mcp.py
```

依赖项目虚拟环境，需先运行过一次 `start-windows.bat`（或手动装好依赖）。