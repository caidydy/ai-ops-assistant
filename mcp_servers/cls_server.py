"""腾讯云 CLS (Cloud Log Service) MCP Server

本地实现的 CLS 日志服务 MCP Server，提供日志查询、检索、告警分析等功能。

模拟数据说明（与 aiops-docs/ 下的经验文档场景对齐）：
- 主题: 数据同步服务(data-sync-service) 应用日志/错误日志、API 网关日志
- 告警: describe_alarms 返回 2~3 条「活跃」告警，触发时间基于当前时间动态生成，
  日志与指标数据在同一时间窗内可查到，Agent 可完成 告警->日志->指标 的完整分析。
"""

import logging
import functools
import json
import random
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from fastmcp import FastMCP

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CLS_MCP_Server")

mcp = FastMCP("CLS")


def log_tool_call(func):
    """装饰器：记录工具调用的日志，包括方法名、参数和返回状态"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        method_name = func.__name__

        # 记录调用信息
        logger.info(f"=" * 80)
        logger.info(f"调用方法: {method_name}")

        # 记录参数（排除self等）
        if kwargs:
            # 使用 json.dumps 格式化参数，处理可能的序列化错误
            try:
                params_str = json.dumps(kwargs, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                params_str = str(kwargs)
            logger.info(f"参数信息:\n{params_str}")
        else:
            logger.info("参数信息: 无")

        # 执行方法
        try:
            result = func(*args, **kwargs)

            # 记录返回状态
            logger.info(f"返回状态: SUCCESS")

            # 记录返回结果摘要（避免日志过长）
            if isinstance(result, dict):
                summary = {k: v if not isinstance(v, (list, dict)) else f"<{type(v).__name__} with {len(v)} items>"
                          for k, v in list(result.items())[:5]}
                logger.info(f"返回结果摘要: {json.dumps(summary, ensure_ascii=False)}")
            else:
                logger.info(f"返回结果: {result}")

            logger.info(f"=" * 80)
            return result

        except Exception as e:
            # 记录错误状态
            logger.error(f"返回状态: ERROR")
            logger.error(f"错误信息: {str(e)}")
            logger.error(f"=" * 80)
            raise

    return wrapper


def parse_time_or_default(time_str: Optional[str], default_offset_hours: int = 0) -> datetime:
    """解析时间字符串或返回默认时间。

    Args:
        time_str: 时间字符串（格式：YYYY-MM-DD HH:MM:SS）
        default_offset_hours: 默认时间偏移（小时）

    Returns:
        datetime: 解析后的时间对象
    """
    if time_str:
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.now() + timedelta(hours=default_offset_hours)


def generate_time_series(base_time: datetime, minutes_offset: int) -> str:
    """生成基于基准时间的时间字符串。

    Args:
        base_time: 基准时间
        minutes_offset: 分钟偏移量

    Returns:
        str: 格式化的时间字符串
    """
    result_time = base_time + timedelta(minutes=minutes_offset)
    return result_time.strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# 模拟数据（告警 + 主题 + 日志），时间基于当前时刻动态生成，
# 保证「告警触发时间 / 日志时间窗 / 指标时间窗」彼此自洽。
# ============================================================

# 主题目录：search_log / get_topic_info_by_name 共用
MOCK_TOPICS = [
    {
        "topic_id": "topic-001",
        "topic_name": "数据同步服务日志",
        "service_name": "data-sync-service",
        "region_code": "ap-beijing",
        "create_time": "2024-01-01 10:00:00",
        "log_count": 0,
        "description": "数据同步服务的应用日志，包含同步任务执行情况",
    },
    {
        "topic_id": "topic-002",
        "topic_name": "数据同步服务错误日志",
        "service_name": "data-sync-service",
        "region_code": "ap-beijing",
        "create_time": "2024-01-01 10:00:00",
        "log_count": 0,
        "description": "数据同步服务的错误日志",
    },
    {
        "topic_id": "topic-003",
        "topic_name": "API网关服务日志",
        "service_name": "api-gateway-service",
        "region_code": "ap-shanghai",
        "create_time": "2024-01-01 10:00:00",
        "log_count": 0,
        "description": "API网关服务日志",
    },
]

# 日志模板：按 topic 区分，混合级别；ERROR 与 WARNING 用于支撑告警分析
LOG_TEMPLATES: Dict[str, List[tuple]] = {
    "topic-001": [
        ("INFO", "正在同步元数据……"),
        ("INFO", "同步任务执行成功，处理 128 条记录"),
        ("INFO", "批次同步完成，耗时 230ms"),
        ("WARNING", "同步延迟超过阈值：3.2s"),
        ("WARNING", "目标端响应较慢，已重试 1 次"),
        ("ERROR", "数据库连接失败，正在重试"),
        ("ERROR", "上游服务超时：read timeout 5s"),
        ("INFO", "API 网关请求完成，耗时 45ms"),
        ("INFO", "心跳正常，offset 已提交"),
        ("ERROR", "消息解析失败：invalid payload"),
    ],
    "topic-002": [
        ("ERROR", "数据库连接失败：Connection refused (127.0.0.1:3306)"),
        ("ERROR", "上游服务超时：read timeout 5s，任务 sync-order-20260808 重试中"),
        ("ERROR", "消息解析失败：invalid payload，已丢弃消息 msg-88213"),
        ("ERROR", "同步批次失败：task sync-order 失败于 offset 1280"),
        ("WARNING", "同步延迟超过阈值：3.2s，目标端为 MySQL 从库"),
        ("ERROR", "数据库连接失败：Too many connections，连接池已满"),
        ("INFO", "连接池回收完成，释放 16 个空闲连接"),
        ("ERROR", "上游服务超时：write timeout，HTTP 503 from api-gateway"),
    ],
    "topic-003": [
        ("INFO", "GET /api/v1/orders 200 45ms"),
        ("INFO", "POST /api/v1/sync/trigger 201 120ms"),
        ("WARNING", "GET /api/v1/orders 499 2100ms 客户端断开"),
        ("INFO", "GET /api/v1/orders 200 38ms"),
        ("ERROR", "POST /api/v1/sync/trigger 502 上游服务不可用"),
        ("INFO", "心跳正常 200 12ms"),
    ],
}


def _fmt(ts_ms: int) -> str:
    """毫秒时间戳 -> 可读时间字符串。"""
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _now_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


def build_mock_alarms() -> List[Dict[str, Any]]:
    """构建活跃告警列表（触发时间相对当前动态生成，保证每次演示都是「活跃」告警）。"""
    now_ms = _now_ms()
    # 各告警的触发时刻（相对当前时间的偏移，毫秒）
    spec = [
        {
            "alarm_id": "alarm-1001",
            "alarm_name": "mock-all-logs-alarm",
            "level": "紧急",
            "level_code": 2,
            "topic_id": "topic-001",
            "service_name": "data-sync-service",
            "status": "活跃",
            "trigger_ms": now_ms - 42 * 60 * 1000,
            "query": "level:ERROR",
            "description": "日志检索命中 level:ERROR 数量超过阈值，每分钟统计 ≥1 条即触发",
        },
        {
            "alarm_id": "alarm-1002",
            "alarm_name": "mock-data-sync-error-alarm",
            "level": "严重",
            "level_code": 1,
            "topic_id": "topic-002",
            "service_name": "data-sync-service",
            "status": "活跃",
            "trigger_ms": now_ms - 26 * 60 * 1000,
            "query": "level:ERROR",
            "description": "数据同步任务连续失败，错误日志数量超过阈值",
        },
        {
            "alarm_id": "alarm-1003",
            "alarm_name": "mock-high-cpu-alarm",
            "level": "警告",
            "level_code": 0,
            "topic_id": "topic-001",
            "service_name": "data-sync-service",
            "status": "活跃",
            "trigger_ms": now_ms - 58 * 60 * 1000,
            "query": "cpu_usage > 80",
            "description": "服务 CPU 使用率持续 5 分钟超过 80%",
        },
    ]
    return spec


def _alarm_to_dict(alarm: Dict[str, Any]) -> Dict[str, Any]:
    """告警记录 -> 对外输出结构（时间转可读字符串）。"""
    trigger_ms = int(alarm["trigger_ms"])
    now_ms = _now_ms()
    duration_sec = max(0, int((now_ms - trigger_ms) / 1000))
    minutes, seconds = divmod(duration_sec, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        duration = f"{hours}小时{minutes}分钟"
    elif minutes:
        duration = f"{minutes}分钟{seconds}秒"
    else:
        duration = f"{seconds}秒"
    return {
        "alarm_id": alarm["alarm_id"],
        "alarm_name": alarm["alarm_name"],
        "alarm_level": alarm["level"],
        "level_code": alarm["level_code"],
        "status": alarm["status"],
        "target": {
            "service_name": alarm["service_name"],
            "topic_id": alarm["topic_id"],
            "query": alarm["query"],
        },
        "first_trigger_time": _fmt(trigger_ms),
        "last_trigger_time": _fmt(trigger_ms + 2 * 60 * 1000),
        "duration": duration,
        "description": alarm["description"],
    }


def _alarm_by_id(alarm_id: str) -> Optional[Dict[str, Any]]:
    for alarm in build_mock_alarms():
        if alarm["alarm_id"] == alarm_id:
            return alarm
    return None


def _parse_cls_query(query: Optional[str]) -> List[str]:
    """极简 CLS 查询解析：抽出 level / message 关键词（支持 level:ERROR、message:xxx 等）。"""
    if not query:
        return []
    keywords: List[str] = []
    for token in query.replace("(", " ").replace(")", " ").split():
        if ":" in token:
            field, _, value = token.partition(":")
            value = value.strip('"').strip("'")
            if field == "level":
                keywords.append(value.lower())
            elif field == "message":
                keywords.append(value.lower())
        elif token.upper() in ("AND", "OR"):
            continue
        else:
            keywords.append(token.lower())
    return [k for k in keywords if k]


def _match_log(log: Dict[str, Any], keywords: List[str]) -> bool:
    """按解析出的关键词过滤单条日志（level / message 命中任一即匹配）。"""
    if not keywords:
        return True
    haystack = f"{str(log.get('level', '')).lower()} {str(log.get('message', '')).lower()}"
    return any(k in haystack for k in keywords)


def build_topic_logs(
    topic_id: str,
    start_time: int,
    end_time: int,
    query: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """按主题生成指定时间窗内的日志，支持 level:ERROR 等关键词过滤。

    模拟真实日志分布：topic-001 混合级别；topic-002 以 ERROR/WARNING 为主；
    时间窗按分钟粒度铺日志，保证告警时间窗内一定能检索到对应级别的日志。
    """
    templates = LOG_TEMPLATES.get(topic_id)
    if not templates:
        return []

    keywords = _parse_cls_query(query)
    logs: List[Dict[str, Any]] = []
    current_ms = start_time
    idx = 0
    while current_ms <= end_time and len(logs) < limit:
        level, message = templates[idx % len(templates)]
        log = {
            "timestamp": _fmt(current_ms),
            "level": level,
            "message": message,
            "topic_id": topic_id,
        }
        if _match_log(log, keywords):
            logs.append(log)
        idx += 1
        current_ms += 60 * 1000  # 每分钟一条
    return logs


@mcp.tool()
@log_tool_call
def get_current_timestamp() -> int:
    """获取当前时间戳（以毫秒为单位）。
    
    此工具用于获取标准的毫秒时间戳，可用于：
    1. 作为 search_log 的 end_time 参数（查询到现在）
    2. 计算历史时间点作为 start_time 参数
    
    Returns:
        int: 当前时间戳（毫秒），例如: 1708012345000
    
    使用示例:
        # 获取当前时间
        current = get_current_timestamp()
        
        # 计算15分钟前的时间
        fifteen_min_ago = current - (15 * 60 * 1000)
        
        # 计算1小时前的时间
        one_hour_ago = current - (60 * 60 * 1000)
        
        # 用于搜索最近15分钟的日志
        search_log(
            topic_id="topic-001",
            start_time=fifteen_min_ago,
            end_time=current
        )
    """
    return int(datetime.now().timestamp() * 1000)


@mcp.tool()
@log_tool_call
def get_region_code_by_name(region_name: str) -> Dict[str, Any]:
    """根据地区名称搜索对应的地区参数。

    Args:
        region_name: 地区名称（如：北京、上海、广州等）

    Returns:
        Dict: 包含地区代码和相关信息的字典
            - region_code: 地区代码
            - region_name: 地区名称
            - available: 是否可用
    """
    # 模拟地区映射表（实际应该从配置或数据库读取）
    region_mapping = {
        "北京": {"region_code": "ap-beijing", "region_name": "北京", "available": True},
        "上海": {"region_code": "ap-shanghai", "region_name": "上海", "available": True},
        "广州": {"region_code": "ap-guangzhou", "region_name": "广州", "available": True},
    }

    result = region_mapping.get(region_name)
    if result:
        return result
    else:
        return {
            "region_code": None,
            "region_name": region_name,
            "available": False,
            "error": f"未找到地区: {region_name}"
        }


@mcp.tool()
@log_tool_call
def get_topic_info_by_name(topic_name: str, region_code: Optional[str] = None) -> Dict[str, Any]:
    """根据主题名称搜索相关的主题信息。

    Args:
        topic_name: 主题名称
        region_code: 地区代码（可选）

    Returns:
        Dict: 包含主题信息的字典
            - topic_id: 主题ID
            - topic_name: 主题名称
            - region_code: 所属地区
            - create_time: 创建时间
            - log_count: 日志数量
    """
    # 根据名称和地区筛选
    for topic in MOCK_TOPICS:
        if topic["topic_name"] == topic_name:
            if region_code is None or topic["region_code"] == region_code:
                return topic

    return {
        "topic_id": None,
        "topic_name": topic_name,
        "region_code": region_code,
        "error": f"未找到主题: {topic_name}"
    }


@mcp.tool()
@log_tool_call
def search_topic_by_service_name(
    service_name: str,
    region_code: Optional[str] = None,
    fuzzy: bool = True
) -> Dict[str, Any]:
    """根据服务名称搜索相关的日志主题信息，支持模糊搜索。
    
    此工具用于根据服务名称查找对应的日志主题（topic），便于后续进行日志查询。
    
    Args:
        service_name: 服务名称（必填）
            示例: "data-sync-service", "sync", "data-sync"
            说明: 当 fuzzy=True 时，支持部分匹配
        
        region_code: 地区代码（可选）
            示例: "ap-beijing", "ap-shanghai"
            说明: 如果指定，只返回该地区的主题
        
        fuzzy: 是否启用模糊搜索（可选，默认 True）
            True: 部分匹配，例如 "sync" 可以匹配 "data-sync-service"
            False: 精确匹配，必须完全一致
    
    Returns:
        Dict: 搜索结果
            - total: 匹配到的主题数量
            - topics: 主题列表，每个主题包含:
                * topic_id: 主题ID（用于后续日志查询）
                * topic_name: 主题名称
                * service_name: 服务名称
                * region_code: 所属地区
                * create_time: 创建时间
                * log_count: 日志数量
                * description: 主题描述
            - query: 查询条件
    
    使用示例:
        # 示例1: 模糊搜索（推荐）
        search_topic_by_service_name(service_name="data-sync")
        # 可以匹配: "data-sync-service", "data-sync-worker" 等
        
        # 示例2: 精确搜索
        search_topic_by_service_name(
            service_name="data-sync-service",
            fuzzy=False
        )
        
        # 示例3: 指定地区搜索
        search_topic_by_service_name(
            service_name="sync",
            region_code="ap-beijing"
        )
        
        # 示例4: 查找后进行日志搜索的完整流程
        # 步骤1: 根据服务名查找 topic
        result = search_topic_by_service_name(service_name="data-sync-service")
        
        # 步骤2: 获取 topic_id
        topic_id = result["topics"][0]["topic_id"]  # "topic-001"
        
        # 步骤3: 使用 topic_id 查询日志
        current_ts = get_current_timestamp()
        start_ts = current_ts - (15 * 60 * 1000)
        search_log(
            topic_id=topic_id,
            start_time=start_ts,
            end_time=current_ts
        )
    """
    # Mock 主题数据（实际应该从配置或数据库读取）
    mock_topics = MOCK_TOPICS
    
    matched_topics = []
    
    # 搜索逻辑
    for topic in mock_topics:
        # 地区筛选
        if region_code and topic["region_code"] != region_code:
            continue
        
        # 服务名称匹配
        topic_service_name = topic.get("service_name", "")
        
        if fuzzy:
            # 模糊匹配：服务名包含查询字符串，或查询字符串包含服务名
            if (service_name.lower() in topic_service_name.lower() or 
                topic_service_name.lower() in service_name.lower()):
                matched_topics.append(topic)
        else:
            # 精确匹配
            if topic_service_name == service_name:
                matched_topics.append(topic)
    
    return {
        "total": len(matched_topics),
        "topics": matched_topics,
        "query": {
            "service_name": service_name,
            "region_code": region_code,
            "fuzzy": fuzzy
        },
        "message": f"找到 {len(matched_topics)} 个匹配的日志主题" if matched_topics else f"未找到服务 '{service_name}' 的日志主题"
    }


@mcp.tool()
@log_tool_call
def search_log(
    topic_id: str,
    start_time: int,
    end_time: int,
    query: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """基于提供的查询参数搜索日志。

    Args:
        topic_id: 主题ID（必填）
            示例: "topic-001"
        
        start_time: 开始时间戳，单位为毫秒（必填，int类型）
            重要: 必须传递整数类型的毫秒时间戳
            获取方式: 
            1. 使用 get_current_timestamp() 工具获取当前时间戳
            2. 计算历史时间: current_timestamp - (分钟数 * 60 * 1000)
            示例: 
            - 当前时间: 1708012345000
            - 15分钟前: 1708012345000 - (15 * 60 * 1000) = 1708011445000
            - 1小时前: 1708012345000 - (60 * 60 * 1000) = 1708008745000
        
        end_time: 结束时间戳，单位为毫秒（必填，int类型）
            重要: 必须传递整数类型的毫秒时间戳
            通常使用 get_current_timestamp() 工具获取当前时间作为结束时间
            示例: 1708012345000
        
        query: 查询语句（可选，CLS 查询语法）
            示例: "level:ERROR" 或 "message:异常"
        
        limit: 返回结果数量限制（默认100，可选）

    Returns:
        Dict: 搜索结果
            - topic_id: 主题ID
            - start_time: 开始时间戳
            - end_time: 结束时间戳
            - query: 查询语句
            - limit: 结果限制
            - total: 实际返回的日志条数
            - logs: 日志列表，每条日志包含:
                * timestamp: 日志时间（格式: YYYY-MM-DD HH:MM:SS）
                * level: 日志级别
                * message: 日志内容
            - took_ms: 查询耗时（毫秒）
            - message: 查询状态消息
    
    使用示例:
        # 步骤1: 获取当前时间戳
        current_ts = get_current_timestamp()  # 返回: 1708012345000
        
        # 步骤2: 计算开始时间（15分钟前）
        start_ts = current_ts - (15 * 60 * 1000)  # 1708011445000
        
        # 步骤3: 搜索日志
        search_log(
            topic_id="topic-001",
            start_time=start_ts,     # int类型: 1708011445000
            end_time=current_ts,     # int类型: 1708012345000
            limit=100
        )
    """
    # 按主题在时间窗内生成日志，并应用 query 关键词过滤
    logs = build_topic_logs(topic_id, start_time, end_time, query, limit)

    if not logs:
        exists = any(t["topic_id"] == topic_id for t in MOCK_TOPICS)
        if not exists:
            return {
                "topic_id": topic_id,
                "start_time": start_time,
                "end_time": end_time,
                "query": query,
                "limit": limit,
                "total": 0,
                "logs": [],
                "took_ms": 0,
                "error": f"主题不存在: {topic_id}",
                "message": f"错误: 未找到主题 {topic_id}，请检查 topic_id 是否正确",
            }
        return {
            "topic_id": topic_id,
            "start_time": start_time,
            "end_time": end_time,
            "query": query,
            "limit": limit,
            "total": 0,
            "logs": [],
            "took_ms": 10,
            "message": f"未检索到符合查询条件（{query or '全部'}）的日志",
        }

    # 按时间倒序，最新的日志在前，便于 Agent 查看最近症状
    logs_sorted = sorted(logs, key=lambda x: x["timestamp"], reverse=True)
    return {
        "topic_id": topic_id,
        "start_time": start_time,
        "end_time": end_time,
        "query": query,
        "limit": limit,
        "total": len(logs_sorted),
        "logs": logs_sorted,
        "took_ms": 50,
        "message": f"成功查询 {len(logs_sorted)} 条日志（主题 {topic_id}）",
    }


@mcp.tool()
@log_tool_call
def describe_alarms(status: Optional[str] = "活跃", limit: int = 20) -> Dict[str, Any]:
    """查询当前活跃的告警列表（模拟 CLS DescribeAlarms）。

    适用场景：AIOps 诊断入口，用于拉取当前系统所有活跃告警，作为根因分析的起点。
    无需用户提供参数，直接调用即可获得告警名称、级别、目标服务、触发时间等。

    Args:
        status: 告警状态筛选（默认 "活跃"；传 "全部" 返回所有模拟告警）
        limit: 返回条数上限

    Returns:
        Dict: 告警列表
            - total: 告警总数
            - alarms: 每条含 alarm_id / alarm_name / alarm_level / status / target /
              first_trigger_time / last_trigger_time / duration / description
    """
    alarms = build_mock_alarms()
    if status and status != "全部":
        alarms = [a for a in alarms if a["status"] == status]
    result = [_alarm_to_dict(a) for a in alarms[:limit]]
    return {
        "total": len(result),
        "alarms": result,
        "message": f"查询到 {len(result)} 条{'活跃' if status == '活跃' else ''}告警",
    }


@mcp.tool()
@log_tool_call
def describe_alert_record_history(
    alarm_id: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """查询指定告警的历史触发记录（模拟 CLS DescribeAlertRecordHistory）。

    Args:
        alarm_id: 告警 ID（来自 describe_alarms）
        start_time: 开始时间戳（毫秒，可选，默认最近 2 小时）
        end_time: 结束时间戳（毫秒，可选，默认当前时间）
        limit: 返回记录条数上限

    Returns:
        Dict: 触发记录列表，每条含 record_id / alarm_name / status / trigger_time /
              alert_condition / topic_id / query
    """
    alarm = _alarm_by_id(alarm_id)
    if not alarm:
        return {
            "alarm_id": alarm_id,
            "total": 0,
            "records": [],
            "error": f"未找到告警: {alarm_id}",
        }

    end_ms = end_time or _now_ms()
    start_ms = start_time or (end_ms - 2 * 60 * 60 * 1000)
    trigger_ms = int(alarm["trigger_ms"])
    # 触发点落在查询时间窗内才返回记录
    records = []
    if start_ms <= trigger_ms <= end_ms:
        records.append(
            {
                "record_id": f"rec-{alarm['alarm_id']}-01",
                "alarm_id": alarm["alarm_id"],
                "alarm_name": alarm["alarm_name"],
                "status": "firing",
                "trigger_time": _fmt(trigger_ms),
                "recover_time": "未恢复",
                "alert_condition": alarm["query"],
                "topic_id": alarm["topic_id"],
                "query": alarm["query"],
                "hit_count": random.randint(3, 12),
            }
        )
    return {
        "alarm_id": alarm_id,
        "total": len(records),
        "records": records,
        "message": f"查询到 {len(records)} 条触发记录" if records else "该时间窗内无触发记录",
    }


@mcp.tool()
@log_tool_call
def get_alarm_log(
    alarm_id: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """获取告警触发时相关的关键日志证据（模拟 CLS GetAlarmLog）。

    返回与告警同时间窗、同主题、同检索条件命中的日志，作为根因分析的直接证据。

    Args:
        alarm_id: 告警 ID（来自 describe_alarms）
        start_time: 开始时间戳（毫秒，可选，默认告警触发前 30 分钟）
        end_time: 结束时间戳（毫秒，可选，默认告警触发时刻）
        limit: 返回日志条数上限

    Returns:
        Dict: 日志证据列表，每条含 timestamp / level / message / topic_id
    """
    alarm = _alarm_by_id(alarm_id)
    if not alarm:
        return {
            "alarm_id": alarm_id,
            "total": 0,
            "logs": [],
            "error": f"未找到告警: {alarm_id}",
        }

    trigger_ms = int(alarm["trigger_ms"])
    end_ms = end_time or trigger_ms
    start_ms = start_time or (end_ms - 30 * 60 * 1000)
    logs = build_topic_logs(alarm["topic_id"], start_ms, end_ms, alarm["query"], limit)
    logs_sorted = sorted(logs, key=lambda x: x["timestamp"], reverse=True)
    return {
        "alarm_id": alarm_id,
        "alarm_name": alarm["alarm_name"],
        "topic_id": alarm["topic_id"],
        "query": alarm["query"],
        "total": len(logs_sorted),
        "logs": logs_sorted,
        "message": f"获取到 {len(logs_sorted)} 条与告警 {alarm['alarm_name']} 相关的日志",
    }



if __name__ == "__main__":
    import os

    # 端口可通过环境变量覆盖（Windows 上 8103 常被 Hyper-V 保留段占用）
    port = int(os.environ.get("CLS_MOCK_PORT", "8383"))
    mcp.run(transport="streamable-http", host="127.0.0.1", port=port, path="/mcp")
