"""智能运维监控 MCP Server

本地实现的监控服务 MCP Server，提供：
- 监控数据查询（CPU、内存、磁盘、网络等）
- 进程信息查询
- 历史工单查询
- 服务信息查询

用于支持运维 Agent 的故障排查场景。
"""

import logging
import functools
import json
import random
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from fastmcp import FastMCP

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Monitor_MCP_Server")

mcp = FastMCP("Monitor")


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


# ============================================================
# 辅助函数
# ============================================================

# 指标生成的基线：与 mcp_servers/cls_server.py 中的 mock 告警时间自洽。
# CPU/内存从正常值逐步爬升，最终超过告警阈值，便于 Agent 用指标佐证告警症状。
METRIC_PROFILES: Dict[str, Dict[str, Any]] = {
    "cpu_usage_percent": {
        "base": 20.0,
        "cap": 95.0,
        "threshold": 80.0,
        "unit": "%",
        "detail_key": "process_id",
        "detail_value": "pid-12345",
    },
    "memory_usage_percent": {
        "base": 40.0,
        "cap": 88.0,
        "threshold": 75.0,
        "unit": "%",
        "detail_key": "used_gb",
        "detail_value": 7.0,
        "detail2_key": "total_gb",
        "detail2_value": 8.0,
    },
    "error_rate_percent": {
        "base": 1.0,
        "cap": 55.0,
        "threshold": 20.0,
        "unit": "%",
        "detail_key": "error_count",
        "detail_value": 0,
    },
    "request_latency_ms": {
        "base": 120.0,
        "cap": 4800.0,
        "threshold": 2000.0,
        "unit": "ms",
        "detail_key": "p99",
        "detail_value": 0,
    },
}

# 各服务支持查询的指标（未知组合返回空数据而非报错）
SERVICE_METRICS: Dict[str, List[str]] = {
    "data-sync-service": ["cpu_usage_percent", "memory_usage_percent", "error_rate_percent", "request_latency_ms"],
    "api-gateway-service": ["cpu_usage_percent", "memory_usage_percent", "error_rate_percent", "request_latency_ms"],
}


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
    # 返回默认时间（当前时间 + 偏移）
    return datetime.now() + timedelta(hours=default_offset_hours)


def generate_time_series(base_time: datetime, minutes_offset: int, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """生成时间序列字符串。

    Args:
        base_time: 基准时间
        minutes_offset: 分钟偏移量
        format_str: 时间格式字符串

    Returns:
        str: 格式化的时间字符串
    """
    result_time = base_time + timedelta(minutes=minutes_offset)
    return result_time.strftime(format_str)





# ============================================================
# 监控数据查询工具
# ============================================================

@mcp.tool()
@log_tool_call
def query_cpu_metrics(
    service_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    interval: str = "1m"
) -> Dict[str, Any]:
    """查询服务的 CPU 使用率监控数据。

    Args:
        service_name: 服务名称（必填）
            示例: "data-sync-service"
        
        start_time: 开始时间（可选，字符串类型）
            格式: "YYYY-MM-DD HH:MM:SS"
            示例: "2026-02-14 10:00:00"
            默认值: 如果不传，默认为当前时间的1小时前
            注意: 必须使用字符串格式，而非时间戳
        
        end_time: 结束时间（可选，字符串类型）
            格式: "YYYY-MM-DD HH:MM:SS"
            示例: "2026-02-14 11:00:00"
            默认值: 如果不传，默认为当前时间
            注意: 必须使用字符串格式，而非时间戳
        
        interval: 数据聚合间隔（可选）
            可选值: "1m" (1分钟), "5m" (5分钟), "1h" (1小时)
            默认值: "1m"
            说明: 控制数据点的时间间隔

    Returns:
        Dict: CPU 监控数据
            - service_name: 服务名称
            - metric_name: 指标名称 (cpu_usage_percent)
            - interval: 数据聚合间隔
            - data_points: 数据点列表，每个点包含:
                * timestamp: 时间点（格式: HH:MM）
                * value: CPU 使用率百分比
            - statistics: 统计信息
                * average: 平均值
                * max: 最大值
                * min: 最小值
            - alert: 告警信息（如有）
                * triggered: 是否触发告警
                * threshold: 告警阈值
                * message: 告警消息
    
    使用示例:
        # 示例1: 使用默认时间（最近1小时）
        query_cpu_metrics(service_name="data-sync-service")
        
        # 示例2: 指定时间范围
        query_cpu_metrics(
            service_name="data-sync-service",
            start_time="2026-02-14 10:00:00",
            end_time="2026-02-14 11:00:00",
            interval="5m"
        )
        
        # 示例3: 只指定开始时间（结束时间自动为当前时间）
        query_cpu_metrics(
            service_name="data-sync-service",
            start_time="2026-02-14 10:00:00"
        )
    """
    # 解析时间参数
    start_dt = parse_time_or_default(start_time, default_offset_hours=-1)
    end_dt = parse_time_or_default(end_time, default_offset_hours=0)
    
    # 解析间隔时间（interval: 1m, 5m, 1h 等）
    interval_minutes = 1  # 默认 1 分钟
    if interval.endswith('m'):
        interval_minutes = int(interval[:-1])
    elif interval.endswith('h'):
        interval_minutes = int(interval[:-1]) * 60

    # 动态生成 CPU 使用率数据：从低到高逐渐增长
    data_points = []
    current_time = start_dt
    time_index = 0

    # 初始 CPU 使用率（10%）
    base_cpu = 10.0

    while current_time <= end_dt:
        # CPU 使用率逐渐升高的算法：
        # - 前几个数据点保持在 10% 左右
        # - 然后开始快速上升
        # - 最终达到 95% 左右

        if time_index < 3:
            # 初始阶段：10% 左右波动
            cpu_value = base_cpu + (time_index * 0.5)
        else:
            # 上升阶段：使用指数增长模型
            growth_factor = (time_index - 2) * 8.5
            cpu_value = min(base_cpu + growth_factor, 96.0)

        # 添加一些随机波动（±2%）
        cpu_value = round(cpu_value + random.uniform(-2, 2), 1)
        cpu_value = max(0, min(100, cpu_value))  # 确保在 0-100 范围内

        data_point = {
            "timestamp": current_time.strftime("%H:%M"),
            "value": cpu_value,
            "process_id": "pid-12345"
        }

        data_points.append(data_point)

        # 下一个时间点
        current_time += timedelta(minutes=interval_minutes)
        time_index += 1

    # 计算统计信息
    if data_points:
        values = [d["value"] for d in data_points]
        avg_value = round(sum(values) / len(values), 2)
        max_value = max(values)
        min_value = min(values)

        # 检测是否有 CPU 突增（超过 80%）
        spike_detected = max_value > 80.0

        return {
            "service_name": service_name,
            "metric_name": "cpu_usage_percent",
            "interval": interval,
            "data_points": data_points,
            "statistics": {
                "avg": avg_value,
                "max": max_value,
                "min": min_value,
                "p95": round(sorted(values)[int(len(values) * 0.95)] if len(values) > 1 else max_value, 2),
                "spike_detected": spike_detected
            },
            "alert_info": {
                "triggered": spike_detected,
                "threshold": 80.0,
                "message": "CPU 使用率持续超过 80% 阈值" if spike_detected else "CPU 使用率正常"
            }
        }
    else:
        return {
            "service_name": service_name,
            "metric_name": "cpu_usage_percent",
            "interval": interval,
            "data_points": [],
            "statistics": {},
        }


@mcp.tool()
@log_tool_call
def query_memory_metrics(
    service_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    interval: str = "1m"
) -> Dict[str, Any]:
    """查询服务的内存使用监控数据。

    Args:
        service_name: 服务名称（必填）
            示例: "data-sync-service"
        
        start_time: 开始时间（可选，字符串类型）
            格式: "YYYY-MM-DD HH:MM:SS"
            示例: "2026-02-14 10:00:00"
            默认值: 如果不传，默认为当前时间的1小时前
            注意: 必须使用字符串格式，而非时间戳
        
        end_time: 结束时间（可选，字符串类型）
            格式: "YYYY-MM-DD HH:MM:SS"
            示例: "2026-02-14 11:00:00"
            默认值: 如果不传，默认为当前时间
            注意: 必须使用字符串格式，而非时间戳
        
        interval: 数据聚合间隔（可选）
            可选值: "1m" (1分钟), "5m" (5分钟), "1h" (1小时)
            默认值: "1m"

    Returns:
        Dict: 内存监控数据
            - service_name: 服务名称
            - metric_name: 指标名称 (memory_usage_percent)
            - interval: 数据聚合间隔
            - data_points: 数据点列表，每个点包含:
                * timestamp: 时间点（格式: HH:MM）
                * value: 内存使用率百分比
                * used_gb: 已使用内存（GB）
                * total_gb: 总内存（GB）
            - statistics: 统计信息
                * average: 平均值
                * max: 最大值
                * min: 最小值
            - alert: 告警信息（如有）
                * triggered: 是否触发告警
                * threshold: 告警阈值
                * message: 告警消息
    
    使用示例:
        # 示例1: 使用默认时间（最近1小时）
        query_memory_metrics(service_name="data-sync-service")
        
        # 示例2: 指定时间范围
        query_memory_metrics(
            service_name="data-sync-service",
            start_time="2026-02-14 10:00:00",
            end_time="2026-02-14 11:00:00",
            interval="5m"
        )
    """
    # 解析时间参数
    start_dt = parse_time_or_default(start_time, default_offset_hours=-1)
    end_dt = parse_time_or_default(end_time, default_offset_hours=0)
    
    # 解析间隔时间（interval: 1m, 5m, 1h 等）
    interval_minutes = 1  # 默认 1 分钟
    if interval.endswith('m'):
        interval_minutes = int(interval[:-1])
    elif interval.endswith('h'):
        interval_minutes = int(interval[:-1]) * 60
    
    # 动态生成内存使用率数据：从低到高逐渐增长
    data_points = []
    current_time = start_dt
    time_index = 0
    
    # 初始内存使用率（30%）
    base_memory = 30.0
    total_gb = 8.0  # 总内存 8GB
    
    while current_time <= end_dt:
        # 内存使用率逐渐升高的算法：
        # - 前几个数据点保持在 30% 左右
        # - 然后开始逐步上升
        # - 最终达到 85% 左右
        
        if time_index < 3:
            # 初始阶段：30% 左右波动
            memory_value = base_memory + (time_index * 1.0)
        else:
            # 上升阶段：使用线性增长模型（内存增长比 CPU 慢）
            growth_factor = (time_index - 2) * 5.5
            memory_value = min(base_memory + growth_factor, 85.0)
        
        # 添加一些随机波动（±1%）
        memory_value = round(memory_value + random.uniform(-1, 1), 1)
        memory_value = max(0, min(100, memory_value))  # 确保在 0-100 范围内
        
        # 计算已使用内存（GB）
        used_gb = round((memory_value / 100.0) * total_gb, 2)
        
        data_point = {
            "timestamp": current_time.strftime("%H:%M"),
            "value": memory_value,
            "used_gb": used_gb,
            "total_gb": total_gb
        }
        
        data_points.append(data_point)
        
        # 下一个时间点
        current_time += timedelta(minutes=interval_minutes)
        time_index += 1
    
    # 计算统计信息
    if data_points:
        values = [d["value"] for d in data_points]
        avg_value = round(sum(values) / len(values), 2)
        max_value = max(values)
        min_value = min(values)
        
        # 检测是否有内存压力（超过 70%）
        memory_pressure = max_value > 70.0
        
        return {
            "service_name": service_name,
            "metric_name": "memory_usage_percent",
            "interval": interval,
            "data_points": data_points,
            "statistics": {
                "avg": avg_value,
                "max": max_value,
                "min": min_value,
                "p95": round(sorted(values)[int(len(values) * 0.95)] if len(values) > 1 else max_value, 2),
                "memory_pressure": memory_pressure
            },
            "alert_info": {
                "triggered": memory_pressure,
                "threshold": 70.0,
                "message": "内存使用率超过 70% 阈值，存在内存压力" if memory_pressure else "内存使用率正常"
            }
        }
    else:
        return {
            "service_name": service_name,
            "metric_name": "memory_usage_percent",
            "interval": interval,
            "data_points": [],
            "statistics": {},
            "error": "时间范围无效或没有生成数据点"
        }


@mcp.tool()
@log_tool_call
def query_metric(
    service_name: str,
    metric_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    interval: str = "1m"
) -> Dict[str, Any]:
    """通用查询服务的监控指标数据（模拟 QueryMetric）。

    适用场景：AIOps 诊断中补充症状描述，用指标佐证告警根因。
    支持 CPU / 内存 / 错误率 / 请求延迟四类指标，数据从正常值逐步爬升并超过阈值，
    与 mcp_servers/cls_server.py 的模拟告警（如 mock-high-cpu-alarm）时间自洽。

    Args:
        service_name: 服务名称（必填）
            示例: "data-sync-service"、"api-gateway-service"
        metric_name: 指标名称（必填）
            可选: "cpu_usage_percent" / "memory_usage_percent" / "error_rate_percent" / "request_latency_ms"
        start_time: 开始时间（可选，格式 "YYYY-MM-DD HH:MM:SS"，默认当前时间 1 小时前）
        end_time: 结束时间（可选，格式 "YYYY-MM-DD HH:MM:SS"，默认当前时间）
        interval: 聚合间隔（可选，"1m" / "5m" / "1h"，默认 "1m"）

    Returns:
        Dict: 指标监控数据
            - service_name / metric_name / interval
            - data_points: 数据点（timestamp / value，附带进程或容量字段）
            - statistics: avg / max / min / p95 / threshold_crossed
            - alert_info: triggered / threshold / message
    """
    profile = METRIC_PROFILES.get(metric_name)
    if profile is None:
        return {
            "service_name": service_name,
            "metric_name": metric_name,
            "error": f"不支持的指标: {metric_name}",
            "supported_metrics": list(METRIC_PROFILES.keys()),
        }
    allowed = SERVICE_METRICS.get(service_name, [])
    if metric_name not in allowed:
        return {
            "service_name": service_name,
            "metric_name": metric_name,
            "data_points": [],
            "statistics": {},
            "message": f"服务 {service_name} 无指标 {metric_name}，可用指标: {allowed or '（未知服务）'}",
        }

    start_dt = parse_time_or_default(start_time, default_offset_hours=-1)
    end_dt = parse_time_or_default(end_time, default_offset_hours=0)

    interval_minutes = 1
    if interval.endswith("m"):
        interval_minutes = int(interval[:-1])
    elif interval.endswith("h"):
        interval_minutes = int(interval[:-1]) * 60

    data_points = []
    current_time = start_dt
    time_index = 0
    base = float(profile["base"])
    cap = float(profile["cap"])
    unit = profile["unit"]

    while current_time <= end_dt:
        # 前 3 个点维持基线，之后按指标特有斜率爬升到上限
        if time_index < 3:
            value = base + time_index * 0.5
        else:
            slope = {
                "cpu_usage_percent": 8.5,
                "memory_usage_percent": 5.5,
                "error_rate_percent": 4.2,
                "request_latency_ms": 420.0,
            }.get(metric_name, 5.0)
            value = min(base + (time_index - 2) * slope, cap)

        value = round(value + random.uniform(-1, 1), 2)
        value = max(0, value)

        point: Dict[str, Any] = {
            "timestamp": current_time.strftime("%H:%M"),
            "value": value,
            "unit": unit,
        }
        if profile.get("detail_key"):
            point[profile["detail_key"]] = profile["detail_value"]
        if profile.get("detail2_key"):
            point[profile["detail2_key"]] = profile["detail2_value"]
        data_points.append(point)

        current_time += timedelta(minutes=interval_minutes)
        time_index += 1

    if not data_points:
        return {
            "service_name": service_name,
            "metric_name": metric_name,
            "data_points": [],
            "statistics": {},
            "error": "时间范围无效或没有生成数据点",
        }

    values = [d["value"] for d in data_points]
    max_value = max(values)
    threshold = float(profile["threshold"])
    crossed = max_value > threshold

    return {
        "service_name": service_name,
        "metric_name": metric_name,
        "interval": interval,
        "unit": unit,
        "data_points": data_points,
        "statistics": {
            "avg": round(sum(values) / len(values), 2),
            "max": max_value,
            "min": min(values),
            "p95": round(sorted(values)[int(len(values) * 0.95)] if len(values) > 1 else max_value, 2),
            "threshold_crossed": crossed,
        },
        "alert_info": {
            "triggered": crossed,
            "threshold": threshold,
            "message": f"{metric_name} 超过阈值 {threshold}{unit}" if crossed else f"{metric_name} 正常",
        },
    }


if __name__ == "__main__":
    import os

    # 端口可通过环境变量覆盖（Windows 上 8104 常被 Hyper-V 保留段占用）
    port = int(os.environ.get("MONITOR_MOCK_PORT", "8384"))
    mcp.run(transport="streamable-http", host="127.0.0.1", port=port, path="/mcp")
