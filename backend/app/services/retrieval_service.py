"""召回引擎：pgvector 向量 + PG tsvector 关键词，混合打分。

设计文档 §6.2 + docs/architecture/retrieval.md。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger

logger = get_logger(__name__)


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


class RetrievalService:
    """向量 + 关键词混合召回。"""

    # 设计文档 §4.3：0.6 向量 + 0.4 关键词
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
        """为简历建立索引：写 embedding + 关键词，触发器自动建 tsvector。"""
        kw_json = json.dumps(keywords or [], ensure_ascii=False)
        emb_str = "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"
        sql = text(
            """
            INSERT INTO resume_vectors (resume_id, embedding, keywords, updated_at)
            VALUES (:rid, :emb::vector, :kw::jsonb, now())
            ON CONFLICT (resume_id) DO UPDATE
                SET embedding = EXCLUDED.embedding,
                    keywords = EXCLUDED.keywords,
                    updated_at = now()
            """
        )
        try:
            await self.db.execute(
                sql, {"rid": resume_id, "emb": emb_str, "kw": kw_json}
            )
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
        """纯向量召回。query_embedding 已有就直接用，否则需传 EmbeddingService 算。"""
        if query_embedding is None:
            raise BusinessException(
                ErrorCode.RETRIEVAL_FAILED,
                "vector_search 需要 query_embedding 参数",
            )
        emb_str = "[" + ",".join(f"{x:.6f}" for x in query_embedding) + "]"
        sql = text(
            """
            SELECT resume_id,
                   1 - (embedding <=> CAST(:query_vec AS vector)) AS score
            FROM resume_vectors
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:query_vec AS vector)
            LIMIT :top_k
            """
        )
        rows = (await self.db.execute(
            sql, {"query_vec": emb_str, "top_k": top_k}
        )).fetchall()
        return [ResumeScore(resume_id=int(r[0]), score=float(r[1])) for r in rows]

    # ---------- 关键词召回 ----------
    async def keyword_search(
        self, query: str, top_k: int
    ) -> list[ResumeScore]:
        """纯关键词召回（PG tsvector + ts_rank_cd）。

        需要 zhparser 扩展（生产），无 zhparser 时 'simple' 词典兜底（中文按字）。
        """
        # simple vs chinese：默认按文档用 chinese；用户未装则 simple 也能跑
        ts_config = "chinese"
        sql = text(
            f"""
            SELECT resume_id,
                   ts_rank_cd(search_tsv, query) AS score
            FROM resume_vectors, plainto_tsquery('{ts_config}', :query) AS query
            WHERE search_tsv @@ query
            ORDER BY score DESC
            LIMIT :top_k
            """
        )
        try:
            rows = (await self.db.execute(
                sql, {"query": query, "top_k": top_k}
            )).fetchall()
        except Exception as exc:  # noqa: BLE001
            # zhparser 未装 → fallback to simple
            logger.warning(
                "retrieval.chinese_dict_failed_fallback",
                error=str(exc),
            )
            sql2 = text(
                """
                SELECT resume_id,
                       ts_rank_cd(search_tsv, query) AS score
                FROM resume_vectors, plainto_tsquery('simple', :query) AS query
                WHERE search_tsv @@ query
                ORDER BY score DESC
                LIMIT :top_k
                """
            )
            rows = (await self.db.execute(
                sql2, {"query": query, "top_k": top_k}
            )).fetchall()
        return [ResumeScore(resume_id=int(r[0]), score=float(r[1])) for r in rows]

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
