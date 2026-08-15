"""重排服务模块 - 基于阿里云百炼 TextReRank 模型对召回文档重排

在向量检索（Milvus）召回一批候选文档后，使用百炼重排模型
（qwen3-rerank）根据与查询的语义相关性对文档重新排序，
纠正向量召回"只算相似度、不考虑真实相关性"的不足。

参考：https://help.aliyun.com/zh/model-studio/text-rerank-api-reference
"""

from typing import List, Tuple

from dashscope import TextReRank
from langchain_core.documents import Document
from loguru import logger

from app.config import config


class RerankService:
    """重排服务 - 封装百炼 TextReRank API"""

    def __init__(self):
        """初始化重排服务"""
        self.model = config.rerank_model
        self.api_key = config.dashscope_api_key
        self.enabled = config.rerank_enabled

        if not self.enabled:
            logger.info("重排服务已禁用（rerank_enabled=false），检索将直接使用向量召回顺序")
        elif not self.api_key or self.api_key == "your-dashscope-api-key":
            # 避免在未配置密钥时启动报错，调用时兜底为禁用
            logger.warning(
                "未检测到有效的 DASHSCOPE_API_KEY，重排功能将自动降级为向量召回顺序"
            )
            self.enabled = False
        else:
            logger.info(f"重排服务初始化完成: model={self.model}")

    def rerank_documents(
        self,
        query: str,
        documents: List[Document],
        top_n: int | None = None,
    ) -> Tuple[List[Document], List[float]]:
        """
        对召回文档执行重排

        Args:
            query: 用户查询
            documents: 向量召回得到的候选文档列表（LangChain Document）
            top_n: 返回最相关的 N 条文档，None 表示全部返回

        Returns:
            Tuple[List[Document], List[float]]: (重排后的文档列表, 对应的相关性分数列表)

        Raises:
            RuntimeError: 重排调用失败时抛出（由调用方决定兜底策略）
        """
        if not documents:
            return [], []

        # 未启用重排时，直接返回原始顺序与占位分数（分数无意义，仅保证接口一致）
        if not self.enabled:
            return list(documents), [0.0] * len(documents)

        try:
            # 提取文档文本作为候选列表（TextReRank 只接受纯文本）
            texts = [doc.page_content for doc in documents]

            logger.info(
                f"调用重排模型: model={self.model}, 候选文档数={len(texts)}, top_n={top_n}"
            )

            response = TextReRank.call(
                model=self.model,
                api_key=self.api_key,
                query=query,
                documents=texts,
                top_n=top_n if top_n is not None else len(texts),
            )

            # 校验响应
            if not response or not hasattr(response, "output"):
                raise RuntimeError(f"重排响应缺少 output 字段: {response}")

            results = response.output.get("results", [])
            if not results:
                logger.warning("重排模型未返回有效结果，退回向量召回顺序")
                return list(documents), [0.0] * len(documents)

            # 按重排模型给出的顺序重排文档，并收集相关性分数
            reranked_docs: List[Document] = []
            reranked_scores: List[float] = []
            for item in results:
                index = item.get("index")
                if index is None or index >= len(documents):
                    continue
                reranked_docs.append(documents[index])
                reranked_scores.append(float(item.get("relevance_score", 0.0)))

            logger.info(
                f"重排完成: {len(documents)} 条候选 -> {len(reranked_docs)} 条"
            )
            return reranked_docs, reranked_scores

        except Exception as e:
            logger.error(f"重排调用失败: {e}")
            raise RuntimeError(f"重排失败: {e}") from e


# 全局单例
rerank_service = RerankService()