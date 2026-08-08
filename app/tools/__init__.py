"""工具模块 - 供 Agent 调用的各种工具"""

from app.config import config
from app.tools.knowledge_tool import retrieve_knowledge
from app.tools.query_metrics_alerts import query_prometheus_alerts
from app.tools.time_tool import get_current_time


def _build_default_local_agent_tools():
    """构建默认本地工具集。

    始终包含知识库与时间工具；Prometheus 告警工具由
    ``ENABLE_PROMETHEUS_ALERTS`` 控制（方案一接 CLS MCP 时可关闭）。
    """
    tools = [retrieve_knowledge, get_current_time]
    # 保留原有 Prometheus 告警能力；仅在配置关闭时不注册，避免干扰 CLS 告警链路
    if config.enable_prometheus_alerts:
        tools.append(query_prometheus_alerts)
    return tuple(tools)


# 默认本地工具集：凡绑定「知识库 + 时间」的 Agent 应使用此元组
DEFAULT_LOCAL_AGENT_TOOLS = _build_default_local_agent_tools()

__all__ = [
    "DEFAULT_LOCAL_AGENT_TOOLS",
    "retrieve_knowledge",
    "get_current_time",
    "query_prometheus_alerts",
]
