"""召回引擎：纯 Python（numpy cosine + 关键词 Jaccard），不依赖任何 PG 扩展。

SQLite 本地版：embedding 以 numpy float32 字节流存 resume_vectors.embedding，
Python 端算 cosine；关键词存 JSON，Python 端算 Jaccard。数据量小（<1000）性能足够。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.db.models.resume_vector import ResumeVector

logger = get_logger(__name__)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass
class ResumeScore:
    """单条召回结果。"""

    resume_id: int
    score: float

    def to_dict(self) -> dict:
        return {"resume_id": self.resume_id, "score": self.score}


@dataclass
class RetrievalResult:
    """召回结果（含元信息）。"""

    results: list[ResumeScore]
    strategy: str  # VECTOR / KEYWORD / HYBRID
    query: str

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
        }


def _pack(vec: list[float]) -> bytes:
    """numpy float32 数组 → bytes。"""
    return np.asarray(vec, dtype=np.float32).tobytes()


def _unpack(blob: bytes) -> np.ndarray:
    """bytes → numpy float32 数组。"""
    return np.frombuffer(blob, dtype=np.float32)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """cosine 相似度。"""
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _tokenize(text: str) -> set[str]:
    """把文本切成 token 集合：英文按词，中文按相邻二元组。"""
    text = (text or "").lower()
    tokens: set[str] = set(re.findall(r"[a-z0-9_+#.]+", text))
    cjk = _CJK_RE.findall(text)
    tokens.update("".join(cjk[i : i + 2]) for i in range(len(cjk) - 1))
    tokens.discard("")
    return tokens


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class RetrievalService:
    """向量 + 关键词混合召回（纯 Python）。"""

    VECTOR_WEIGHT = 0.6
    KEYWORD_WEIGHT = 0.4

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------- 索引 ----------
    async def index_resume(
        self,
        resume_id: int,
        text_content: str,
        embedding: list[float],
        keywords: list[str] | None = None,
    ) -> None:
        """为简历建立索引：upsert embedding + 关键词。"""
        # 没给关键词时，从原文自动抽 token 兜底
        if keywords is None:
            keywords = sorted(_tokenize(text_content))[:500]

        row = (
            await self.db.execute(
                select(ResumeVector).where(ResumeVector.resume_id == resume_id)
            )
        ).scalar_one_or_none()
        blob = _pack(embedding)

        if row is None:
            self.db.add(
                ResumeVector(
                    resume_id=resume_id,
                    embedding=blob,
                    keywords=keywords,
                )
            )
        else:
            row.embedding = blob
            row.keywords = keywords
        try:
            await self.db.commit()
            logger.info("retrieval.indexed", resume_id=resume_id)
        except Exception as exc:  # noqa: BLE001
            await self.db.rollback()
            raise BusinessException(
                ErrorCode.RETRIEVAL_FAILED, f"建索引失败: {exc}"
            ) from exc

    # ---------- 向量召回 ----------
    async def vector_search(
        self, query: str, top_k: int, query_embedding: list[float] | None = None
    ) -> list[ResumeScore]:
        """纯向量召回：Python 端算 cosine。"""
        if query_embedding is None:
            raise BusinessException(
                ErrorCode.RETRIEVAL_FAILED,
                "vector_search 需要 query_embedding 参数",
            )
        q_vec = np.asarray(query_embedding, dtype=np.float32)

        rows = (
            await self.db.execute(
                select(ResumeVector.resume_id, ResumeVector.embedding).where(
                    ResumeVector.embedding.is_not(None)
                )
            )
        ).fetchall()

        scored: list[ResumeScore] = []
        for rid, blob in rows:
            if not blob:
                continue
            try:
                v = _unpack(blob)
            except Exception:  # noqa: BLE001
                continue
            s = _cosine(q_vec, v)
            scored.append(ResumeScore(resume_id=int(rid), score=s))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    # ---------- 关键词召回 ----------
    async def keyword_search(
        self, query: str, top_k: int
    ) -> list[ResumeScore]:
        """纯关键词召回：对每条已索引简历算 query 与关键词的 Jaccard。"""
        q_tokens = _tokenize(query)

        rows = (
            await self.db.execute(
                select(ResumeVector.resume_id, ResumeVector.keywords)
            )
        ).fetchall()

        scored: list[ResumeScore] = []
        for rid, keywords in rows:
            kw_tokens = _tokenize(" ".join(keywords or []))
            s = _jaccard(q_tokens, kw_tokens)
            if s > 0:
                scored.append(ResumeScore(resume_id=int(rid), score=s))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    # ---------- 混合召回 ----------
    async def hybrid_search(
        self,
        query: str,
        top_k: int,
        query_embedding: list[float] | None = None,
        strategy: str = "HYBRID",
    ) -> RetrievalResult:
        """混合召回主入口。

        strategy: VECTOR / KEYWORD / HYBRID
        """
        if strategy == "VECTOR":
            results = await self.vector_search(
                query, top_k, query_embedding=query_embedding
            )
        elif strategy == "KEYWORD":
            results = await self.keyword_search(query, top_k)
        else:
            # HYBRID：候选池 top_k*2
            cand_k = top_k * 2
            vec = await self.vector_search(
                query, cand_k, query_embedding=query_embedding
            )
            kw = await self.keyword_search(query, cand_k)
            results = self._merge(vec, kw)[:top_k]
        return RetrievalResult(results=results, strategy=strategy, query=query)

    def _merge(
        self, vec: list[ResumeScore], kw: list[ResumeScore]
    ) -> list[ResumeScore]:
        """归一化 + 加权融合。"""
        vec_n = _normalize_scores(vec)
        kw_n = _normalize_scores(kw)
        merged: dict[int, float] = {}
        for r in vec_n:
            merged[r.resume_id] = merged.get(r.resume_id, 0.0) + self.VECTOR_WEIGHT * r.score
        for r in kw_n:
            merged[r.resume_id] = merged.get(r.resume_id, 0.0) + self.KEYWORD_WEIGHT * r.score

        return [
            ResumeScore(resume_id=rid, score=score)
            for rid, score in sorted(merged.items(), key=lambda x: x[1], reverse=True)
        ]


def _normalize_scores(scores: list[ResumeScore]) -> list[ResumeScore]:
    """把分数线性归一化到 [0, 1]。"""
    if not scores:
        return []
    max_s = max(s.score for s in scores)
    if max_s == 0:
        return [ResumeScore(resume_id=s.resume_id, score=0.0) for s in scores]
    return [ResumeScore(resume_id=s.resume_id, score=s.score / max_s) for s in scores]
