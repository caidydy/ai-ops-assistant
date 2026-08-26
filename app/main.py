"""FastAPI 应用入口

主应用程序，配置路由、中间件、静态文件等
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger

from app.api import aiops, chat, file, health
from app.config import config
from app.core.milvus_client import milvus_manager
from app.services.bm25_service import bm25_service
from app.services.rag_agent_service import rag_agent_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("=" * 60)
    logger.info(f"🚀 {config.app_name} v{config.app_version} 启动中...")
    logger.info(f"📝 环境: {'开发' if config.debug else '生产'}")
    logger.info(f"🌐 监听地址: http://{config.host}:{config.port}")
    logger.info(f"📚 API 文档: http://{config.host}:{config.port}/docs")

    # 连接 Milvus
    logger.info("🔌 正在连接 Milvus...")
    milvus_manager.connect()
    logger.info("✅ Milvus 连接成功")

    # 初始化记忆持久化（SQLite 会话历史检查点）
    # from_conn_string 是异步上下文管理器，常驻连接贯穿整个应用生命周期
    # 确保数据库文件所在目录存在，否则 SQLite 报 "unable to open database file"
    memory_db_dir = os.path.dirname(config.memory_db_path)
    if memory_db_dir:
        os.makedirs(memory_db_dir, exist_ok=True)
    checkpointer_ctx = AsyncSqliteSaver.from_conn_string(config.memory_db_path)
    checkpointer = await checkpointer_ctx.__aenter__()
    try:
        await rag_agent_service.set_checkpointer(checkpointer)
        logger.info("✅ 记忆持久化初始化完成（会话历史将持久化到磁盘，重启不丢失）")

        # 重建 BM25 内存索引（混合检索需要，从 Milvus 全量加载）
        if config.hybrid_search_enabled:
            logger.info("🔍 正在重建 BM25 索引...")
            bm25_service.rebuild()
            logger.info("✅ BM25 索引重建完成")

        logger.info("=" * 60)

        yield
    finally:
        # 关闭时执行
        logger.info("🔌 正在关闭 Milvus 连接...")
        milvus_manager.close()
        logger.info("💾 正在关闭记忆持久化连接...")
        await rag_agent_service.close_checkpointer()
        await checkpointer_ctx.__aexit__(None, None, None)
        logger.info(f"👋 {config.app_name} 关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description="基于 LangChain 的智能oncall运维系统",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health.router, tags=["健康检查"])
app.include_router(chat.router, prefix="/api", tags=["对话"])
app.include_router(file.router, prefix="/api", tags=["文件管理"])
app.include_router(aiops.router, prefix="/api", tags=["AIOps智能运维"])

# 挂载静态文件
static_dir = "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    """返回首页"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "message": f"Welcome to {config.app_name} API",
        "version": config.app_version,
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level="info"
    )
