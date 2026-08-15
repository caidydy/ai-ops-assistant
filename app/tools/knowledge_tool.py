"""知识检索工具 - 混合检索（向量 + BM25）→ RRF 融合 → 重排"""

from typing import Dict, List, Tuple

from langchain_core.documents import Document
from langchain_core.tools import tool
from loguru import logger

from app.config import config
from app.services.bm25_service import bm25_service
from app.services.rerank_service import rerank_service
from app.services.vector_store_manager import vector_store_manager


@tool(response_format="content_and_artifact")
def retrieve_knowledge(query: str) -> Tuple[str, List[Document]]:
    """从知识库中检索相关信息来回答问题
    
    当用户的问题涉及专业知识、文档内容或需要参考资料时，使用此工具。
    
    Args:
        query: 用户的问题或查询
        
    Returns:
        Tuple[str, List[Document]]: (格式化的上下文文本, 原始文档列表)
    """
    try:
        logger.info(f"知识检索工具被调用: query='{query}'")
        
        # 1. 混合召回：向量检索 + BM25 词法检索各取 retrieve_k 条候选
        retrieve_k = config.rerank_retrieve_k if config.rerank_enabled else config.rag_top_k

        if config.hybrid_search_enabled:
            vector_store = vector_store_manager.get_vector_store()
            vec_docs = vector_store.as_retriever(
                search_kwargs={"k": retrieve_k}
            ).invoke(query)
            bm25_docs = bm25_service.search(query, k=config.bm25_retrieve_k)

            logger.info(
                f"混合召回: 向量 {len(vec_docs)} 条 + BM25 {len(bm25_docs)} 条"
            )

            # 2. RRF 融合：把两路召回结果按排名融合排序，去重后取前 retrieve_k 条
            docs = rrf_merge(vec_docs, bm25_docs, k=config.rrf_k)
            docs = docs[:retrieve_k]
            logger.info(f"RRF 融合后候选: {len(docs)} 条")
        else:
            # 未启用混合检索：退回纯向量召回（兼容旧行为）
            vector_store = vector_store_manager.get_vector_store()
            docs = vector_store.as_retriever(
                search_kwargs={"k": retrieve_k}
            ).invoke(query)
            logger.info(f"纯向量召回 {len(docs)} 条候选文档")
        
        if not docs:
            logger.warning("未检索到相关文档")
            return "没有找到相关信息。", []
        
        # 3. 重排（纠偏融合排序，只保留最相关的前 rag_top_k 条）
        final_k = config.rerank_final_k
        try:
            reranked_docs, reranked_scores = rerank_service.rerank_documents(
                query=query,
                documents=docs,
                top_n=final_k,
            )
            # 记录重排前后的顺序变化，便于排查
            _log_rerank_order(docs, reranked_docs, reranked_scores)
            docs = reranked_docs
        except Exception as e:
            # 兜底：重排失败时退回融合排序，不阻断问答
            logger.warning(f"重排失败，使用融合排序兜底: {e}")
        
        # 4. 格式化文档为上下文
        context = format_docs(docs)
        
        logger.info(f"最终返回 {len(docs)} 个相关文档")
        return context, docs
        
    except Exception as e:
        logger.error(f"知识检索工具调用失败: {e}")
        return f"检索知识时发生错误: {str(e)}", []


def rrf_merge(
    *doc_lists: List[Document],
    k: int = 60,
) -> List[Document]:
    """
    Reciprocal Rank Fusion (RRF) 融合排序

    核心思想：不依赖各检索器输出的"分数"（不同检索器的分数量纲不同，
    无法直接比较），只依赖"排名"。每个文档在某个检索结果中的名次越靠前，
    贡献的分值越高：

        RRF_score(d) = Σ 1 / (k + rank_i(d))

    其中 rank_i(d) 是文档 d 在第 i 路检索结果中的排名（从 1 开始），
    k 为融合常数（业界标准值 60，控制排名权重的衰减速度）。

    Args:
        doc_lists: 多路检索结果（每路为一个按相关度降序的文档列表）
        k: RRF 融合常数，默认 60

    Returns:
        List[Document]: 按 RRF 分数降序、去重后的文档列表
    """
    scores: Dict[str, float] = {}
    doc_by_key: Dict[str, Document] = {}

    for docs in doc_lists:
        for rank, doc in enumerate(docs, start=1):
            key = doc.page_content  # 用全文做唯一标识（与 _log_rerank_order 一致）
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            doc_by_key[key] = doc  # 后者覆盖前者，内容相同即视为同一文档

    # 按 RRF 分数降序返回
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [doc_by_key[key] for key, _ in ranked]


def _log_rerank_order(
    original: List[Document],
    reranked: List[Document],
    scores: List[float],
) -> None:
    """
    记录重排前后的顺序变化与相关性分数（仅用于日志排查）

    Args:
        original: 融合召回时的原始顺序
        reranked: 重排后的文档顺序
        scores: 重排后的相关性分数
    """
    # 用 id 标识文档（Document.metadata 里没有 id 时退回内容前 20 字）
    def doc_label(doc: Document) -> str:
        file_name = doc.metadata.get("_file_name", "未知来源")
        snippet = doc.page_content[:20].replace("\n", " ")
        return f"{file_name}::{snippet}"

    if not reranked:
        return

    detail = " | ".join(
        f"#{i}(score={score:.4f}): {doc_label(doc)}"
        for i, (doc, score) in enumerate(zip(reranked, scores))
    )
    logger.debug(f"重排顺序: {detail}")

    # 对比原顺序与重排顺序是否一致（id 相同即认为同一文档）
    original_ids = [doc.page_content for doc in original]
    reranked_ids = [doc.page_content for doc in reranked]
    changed = original_ids != reranked_ids
    logger.info(f"重排是否改变顺序: {'是' if changed else '否'}")


def format_docs(docs: List[Document]) -> str:
    """
    格式化文档列表为上下文文本
    
    Args:
        docs: 文档列表
        
    Returns:
        str: 格式化的上下文文本
    """
    formatted_parts = []
    
    for i, doc in enumerate(docs, 1):
        # 提取元数据
        metadata = doc.metadata
        source = metadata.get("_file_name", "未知来源")
        
        # 提取标题信息 (如果有)
        headers = []
        for key in ["h1", "h2", "h3"]:
            if key in metadata and metadata[key]:
                headers.append(metadata[key])
        
        header_str = " > ".join(headers) if headers else ""
        
        # 构建格式化文本
        formatted = f"【参考资料 {i}】"
        if header_str:
            formatted += f"\n标题: {header_str}"
        formatted += f"\n来源: {source}"
        formatted += f"\n内容:\n{doc.page_content}\n"
        
        formatted_parts.append(formatted)
    
    return "\n".join(formatted_parts)