"""自包含验证脚本：内部拉起 mock 服务 → MCP 客户端验证 → 清理。

用法: python scripts/verify_mock_mcp.py
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")

CLS_URL = "http://127.0.0.1:8383/mcp"
MON_URL = "http://127.0.0.1:8384/mcp"


def wait_http(url: str, timeout: float = 20.0) -> bool:
    """等待 HTTP 端点可连接（MCP 端点对 GET 返回非 4xx/5xx 网络错误即可视为就绪）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=2.0)
            return True
        except Exception:
            time.sleep(0.5)
    return False


async def check_server(name: str, url: str, calls: list[tuple[str, dict]]):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    print(f"\n{'=' * 60}\n[{name}] {url}\n{'=' * 60}")
    try:
        async with streamablehttp_client(url) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = sorted(t.name for t in tools.tools)
                print(f"  可用工具 ({len(names)}): {', '.join(names)}\n")
                for tool_name, args_dict in calls:
                    print(f"  --- 调用 {tool_name}({json.dumps(args_dict, ensure_ascii=False)}) ---")
                    try:
                        result = await session.call_tool(tool_name, args_dict)
                        for item in result.content:
                            text = getattr(item, "text", str(item))
                            print(text[:2400])
                            print("  ..." if len(text) > 2400 else "")
                    except Exception as e:
                        print(f"  调用失败: {e}")
                    print()
    except Exception as e:
        print(f"  连接失败: {type(e).__name__}: {e}")


async def main():
    procs = []
    for file, url, tag in [
        ("mcp_servers/cls_server.py", CLS_URL, "CLS"),
        ("mcp_servers/monitor_server.py", MON_URL, "Monitor"),
    ]:
        print(f"[{tag}] 启动服务 {file} ...")
        log_path = ROOT / f"{tag.lower()}_mock.log"
        f = open(log_path, "w", encoding="utf-8")
        p = subprocess.Popen(
            [PYTHON, str(ROOT / file)],
            cwd=str(ROOT),
            stdout=f,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        procs.append(p)
        ok = wait_http(url)
        print(f"[{tag}] 端口就绪: {ok}")
        if not ok:
            log = log_path.read_text(encoding="utf-8", errors="replace")[-1500:]
            print(log)
        time.sleep(1)

    await check_server(
        "CLS mock (8103)",
        CLS_URL,
        [
            ("describe_alarms", {}),
            ("get_topic_info_by_name", {"topic_name": "数据同步服务日志"}),
            ("get_alarm_log", {"alarm_id": "alarm-1002"}),
            ("search_log", {"topic_id": "topic-002", "start_time": 1754392800000, "end_time": 1754396400000, "query": "level:ERROR", "limit": 5}),
        ],
    )
    await check_server(
        "Monitor mock (8104)",
        MON_URL,
        [
            ("query_metric", {"service_name": "data-sync-service", "metric_name": "cpu_usage_percent"}),
        ],
    )

    print("\n清理子进程...")
    for p in procs:
        p.terminate()
    time.sleep(1)
    for p in procs:
        if p.poll() is None:
            p.kill()


if __name__ == "__main__":
    asyncio.run(main())