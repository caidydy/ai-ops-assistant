"""BM25 词法检索服务模块 - 内存 BM25 索引，与 Milvus 向量库保持同步

向量检索（余弦相似度）擅长语义匹配，但对"精确词条"（错误码、接口名、
配置项等）容易漏检。BM25 是经典词法检索算法，按词频/逆文档频率打分，
恰好补足这一短板。两者结合即为混合检索（Hybrid Search）。

本服务维护一个内存 BM25 语料库：
- 应用启动时从 Milvus 全量重建（rebuild）
- 文档入库时增量追加（add_documents）
- 文档删除时按来源文件移除（remove_by_source）
"""

import re
from typing import Dict, List, Optional

from langchain_core.documents import Document
from loguru import logger
from rank_bm25 import BM25Okapi

from app.config import config
from app.core.milvus_client import milvus_manager


class BM25Service:
    """BM25 服务 - 内存词法索引，与 Milvus 向量库同步"""

    def __init__(self) -> None:
        """初始化 BM25 服务（索引为空，等待 rebuild）"""
        self._documents: List[Document] = []
        self._tokenized_corpus: List[List[str]] = []
        self._bm25: Optional[BM25Okapi] = None
        # 词 -> 包含该词的文档下标集合（用于按来源文件快速定位）
        self._source_to_indices: Dict[str, List[int]] = {}

    # ---------------------------------------------------------------
    # 索引构建与同步
    # ---------------------------------------------------------------

    def rebuild(self) -> None:
        """
        从 Milvus 全量重建 BM25 索引

        应用启动时调用一次。知识库为小规模（几百份文档）时秒级完成；
        若 Milvus 不可用或为空，静默降级为空索引（检索退化为纯向量）。
        """
        try:
            collection = milvus_manager.get_collection()
            # 分页读取全部文档（content + metadata 足够重建）
            docs_data: List[dict] = []
            offset = 0
            batch_size = 1000
            while True:
                batch = collection.query(
                    expr="id != ''",
                    output_fields=["content", "metadata"],
                    offset=offset,
                    limit=batch_size,
                )
                docs_data.extend(batch)
                if len(batch) < batch_size:
                    break
                offset += batch_size

            documents: List[Document] = []
            for row in docs_data:
                metadata = row.get("metadata") or {}
                documents.append(
                    Document(page_content=row.get("content", ""), metadata=metadata)
                )

            self._build_index(documents)
            logger.info(
                f"BM25 索引重建完成: 共 {len(documents)} 个分片（来源文件 "
                f"{len(self._source_to_indices)} 个）"
            )
        except Exception as e:
            # 启动阶段 Milvus 未就绪时不应阻断应用启动
            logger.warning(f"BM25 索引重建失败（将退化为纯向量检索）: {e}")
            self._clear()

    def add_documents(self, documents: List[Document]) -> None:
        """
        增量追加文档（入库后调用，与 Milvus 写入保持同步）

        Args:
            documents: 新写入的分片文档列表
        """
        if not documents:
            return
        self._build_index(self._documents + documents)
        logger.debug(f"BM25 索引增量更新: 新增 {len(documents)} 个分片")

    def remove_by_source(self, file_path: str) -> int:
        """
        按来源文件移除对应分片（文件删除/覆盖前调用）

        Args:
            file_path: 来源文件路径（metadata['_source']）

        Returns:
            int: 移除的分片数量
        """
        indices = self._source_to_indices.get(file_path, [])
        if not indices:
            return 0

        # 从集合中按下标倒序删除
        removed_set = set(indices)
        remaining = [
            doc for i, doc in enumerate(self._documents) if i not in removed_set
        ]
        removed_count = len(self._documents) - len(remaining)
        self._build_index(remaining)
        logger.info(
            f"BM25 索引移除来源文件: {file_path}, 移除 {removed_count} 个分片"
        )
        return removed_count

    # ---------------------------------------------------------------
    # 检索
    # ---------------------------------------------------------------

    def search(self, query: str, k: int = 3) -> List[Document]:
        """
        BM25 检索

        Args:
            query: 查询文本
            k: 返回结果数量

        Returns:
            List[Document]: 相关文档列表（与向量侧同构的 Document）
        """
        if not self._bm25 or not query.strip():
            return []

        tokens = self._tokenize(query)
        if not tokens:
            return []

        try:
            scores = self._bm25.get_scores(tokens)
            # 取分数最高的前 k 个（按分数降序）
            ranked = sorted(
                range(len(scores)), key=lambda i: scores[i], reverse=True
            )[:k]
            docs = [self._documents[i] for i in ranked if scores[i] > 0]
            logger.debug(f"BM25 检索完成: query='{query}', 命中 {len(docs)} 条")
            return docs
        except Exception as e:
            logger.error(f"BM25 检索失败: {e}")
            return []

    # ---------------------------------------------------------------
    # 内部实现
    # ---------------------------------------------------------------

    def _build_index(self, documents: List[Document]) -> None:
        """用给定文档列表重建 BM25 索引"""
        self._documents = list(documents)
        self._tokenized_corpus = [self._tokenize(doc.page_content) for doc in documents]
        self._bm25 = BM25Okapi(self._tokenized_corpus) if documents else None

        # 重建来源文件 -> 下标映射
        self._source_to_indices = {}
        for i, doc in enumerate(self._documents):
            source = doc.metadata.get("_source", "")
            if source:
                self._source_to_indices.setdefault(source, []).append(i)

    def _clear(self) -> None:
        """清空索引"""
        self._documents = []
        self._tokenized_corpus = []
        self._bm25 = None
        self._source_to_indices = {}

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """
        轻量中文分词策略：按非字母数字字符切分，保留英文单词/数字与中文单字块

        说明：不做专业分词（如 jieba），因为 BM25 的词频统计对
        "字符 n-gram" 形式同样有效，且零依赖。中文以连续中文字符
        作为一个词元，英文/数字以整词为词元。
        """
        if not text:
            return []
        # 中文连续块（[一-龥]+）或英文/数字词（[a-zA-Z0-9]+）
        return re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", text.lower())


# 全局单例
bm25_service = BM25Service()