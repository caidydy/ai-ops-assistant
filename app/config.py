"""配置管理模块

使用 Pydantic Settings 实现类型安全的配置管理
"""

from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用配置
    app_name: str = "ai-ops-assistant"
    app_version: str = "1.2.1"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 9900

    # DashScope 配置
    dashscope_api_key: str = ""  # 默认空字符串，实际使用需从环境变量加载
    dashscope_model: str = "qwen-max"
    dashscope_embedding_model: str = "text-embedding-v4"  # v4 支持多种维度（默认 1024）

    # Milvus 配置
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_timeout: int = 10000  # 毫秒

    # RAG 配置
    rag_top_k: int = 3
    rag_model: str = "qwen-max"  # 使用快速响应模型，不带扩展思考

    # 对话上下文自动压缩配置（基于 langchain SummarizationMiddleware）
    # 当会话历史 token 数达到上下文窗口的 context_compress_ratio 比例时，
    # 自动调用大模型把早期消息总结成一条摘要，并保留最近 context_keep_messages 条消息
    context_window_tokens: int = 32768  # 模型上下文窗口大小（qwen-max 为 32K）
    context_compress_ratio: float = 0.7  # 触发压缩的上下文占用比例（70% 时触发）
    context_keep_messages: int = 20  # 压缩后保留的最近消息条数（20 条 ≈ 10 轮对话）

    # 记忆持久化配置：使用 SQLite 保存会话历史（LangGraph AsyncSqliteSaver）
    # 服务重启后历史不丢失，用户请求到来时 agent 自动从 DB 检索该会话的历史消息
    memory_db_path: str = "data/memory.db"  # 会话历史 DB 文件路径（相对项目根目录）

    # 重排（Rerank）配置：召回后使用百炼重排模型对文档相关性重新排序
    rerank_enabled: bool = True  # 是否启用重排（关闭时退化为纯向量召回）
    rerank_model: str = "qwen3-rerank"  # 百炼重排模型（gte-rerank 已于 2026-05-30 下线）
    rerank_retrieve_k: int = 6  # 向量召回窗口（扩大召回，重排后截取前 rag_top_k 条）

    @property
    def rerank_final_k(self) -> int:
        """重排后最终返回的文档条数，对齐 rag_top_k"""
        return self.rag_top_k

    # 混合检索配置：向量召回（余弦相似度）+ BM25 词法召回，RRF 融合后送入重排
    hybrid_search_enabled: bool = True  # 是否启用混合检索（关闭时退化纯向量召回）
    bm25_retrieve_k: int = 6  # BM25 召回窗口（与 rerank_retrieve_k 对齐，融合前各取 N 条）
    rrf_k: int = 60  # RRF 融合常数（业界标准值，控制排名权重衰减）

    # 文档分块配置
    chunk_max_size: int = 800
    chunk_overlap: int = 100

    # MCP 服务配置（transport: stdio | sse | streamable-http）
    # 腾讯云托管 MCP 的 URL 通常含 /sse/，需使用 sse；本地 FastMCP 使用 streamable-http
    # 方案一：自建 cls-mcp-server 时使用 sse + http://localhost:3000/sse
    mcp_cls_transport: str = "streamable-http"
    mcp_cls_url: str = "http://localhost:8003/mcp"
    mcp_monitor_transport: str = "streamable-http"
    mcp_monitor_url: str = "http://localhost:8004/mcp"

    # Prometheus（可选；方案一走 CLS DescribeAlarms 时可关闭，避免 Agent 优先打 9090）
    prometheus_base_url: str = "http://127.0.0.1:9090"
    prometheus_request_timeout: float = 10.0
    enable_prometheus_alerts: bool = True

    @property
    def mcp_servers(self) -> dict[str, dict[str, Any]]:
        """获取完整的 MCP 服务器配置"""
        return {
            "cls": {
                "transport": self.mcp_cls_transport,
                "url": self.mcp_cls_url,
            },
            "monitor": {
                "transport": self.mcp_monitor_transport,
                "url": self.mcp_monitor_url,
            }
        }


# 全局配置实例
config = Settings()
