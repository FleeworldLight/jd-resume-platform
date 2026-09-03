"""评估指标：Recall@K / Precision@K / NDCG@K / MRR。

设计文档 §6.5 + docs/modules/customization.md §4（RetrievalMetrics）。
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from app.services.retrieval_service import ResumeScore


@dataclass
class EvalResult:
    """单次评估结果。"""

    recall_at_k: float
    precision_at_k: float
    ndcg_at_k: float
    mrr: float
    k: int
    total_relevant: int
    hit_count: int
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class EvaluationService:
    """纯函数评估器。"""

    @staticmethod
    def recall_at_k(results: list[ResumeScore], ground_truth: set[int], k: int) -> float:
        if not ground_truth:
            return 0.0
        top = [r.resume_id for r in results[:k]]
        hits = sum(1 for rid in top if rid in ground_truth)
        return hits / len(ground_truth)

    @staticmethod
    def precision_at_k(results: list[ResumeScore], ground_truth: set[int], k: int) -> float:
        if k <= 0:
            return 0.0
        top = [r.resume_id for r in results[:k]]
        if not top:
            return 0.0
        hits = sum(1 for rid in top if rid in ground_truth)
        return hits / min(k, len(top))

    @staticmethod
    def ndcg_at_k(results: list[ResumeScore], ground_truth: set[int], k: int) -> float:
        """NDCG@K：相关 = 1，不相关 = 0。"""
        top = [r.resume_id for r in results[:k]]
        dcg = sum(
            (1.0 if rid in ground_truth else 0.0) / math.log2(i + 2)
            for i, rid in enumerate(top)
        )
        ideal_hits = min(len(ground_truth), k)
        idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
        if idcg == 0:
            return 0.0
        return dcg / idcg

    @staticmethod
    def mrr(results: list[ResumeScore], ground_truth: set[int]) -> float:
        """Mean Reciprocal Rank（单 query）。"""
        for i, r in enumerate(results):
            if r.resume_id in ground_truth:
                return 1.0 / (i + 1)
        return 0.0

    def evaluate(
        self,
        results: list[ResumeScore],
        ground_truth: set[int],
        k: int = 10,
    ) -> EvalResult:
        return EvalResult(
            recall_at_k=self.recall_at_k(results, ground_truth, k),
            precision_at_k=self.precision_at_k(results, ground_truth, k),
            ndcg_at_k=self.ndcg_at_k(results, ground_truth, k),
            mrr=self.mrr(results, ground_truth),
            k=k,
            total_relevant=len(ground_truth),
            hit_count=sum(1 for r in results[:k] if r.resume_id in ground_truth),
        )
