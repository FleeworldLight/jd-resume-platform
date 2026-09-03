"""测试：评估指标。"""
from __future__ import annotations

import math

from app.services.evaluation_service import EvaluationService
from app.services.retrieval_service import ResumeScore


def _rs(rid: int, score: float) -> ResumeScore:
    return ResumeScore(resume_id=rid, score=score)


class TestRecall:
    def test_empty(self) -> None:
        assert EvaluationService.recall_at_k([], {1, 2}, 10) == 0.0

    def test_perfect(self) -> None:
        results = [_rs(1, 1.0), _rs(2, 0.9)]
        assert EvaluationService.recall_at_k(results, {1, 2}, 10) == 1.0

    def test_partial(self) -> None:
        results = [_rs(1, 1.0), _rs(3, 0.9), _rs(4, 0.8)]
        # ground_truth={1,2}，召回 1 → 1/2 = 0.5
        assert EvaluationService.recall_at_k(results, {1, 2}, 10) == 0.5

    def test_topk_truncate(self) -> None:
        results = [_rs(1, 1.0), _rs(2, 0.9)]
        # k=1 只看第 1 个
        assert EvaluationService.recall_at_k(results, {1, 2}, 1) == 0.5


class TestPrecision:
    def test_perfect(self) -> None:
        results = [_rs(1, 1.0)]
        assert EvaluationService.precision_at_k(results, {1}, 1) == 1.0

    def test_zero(self) -> None:
        results = [_rs(99, 1.0)]
        assert EvaluationService.precision_at_k(results, {1}, 1) == 0.0

    def test_mixed(self) -> None:
        results = [_rs(1, 1.0), _rs(99, 0.9), _rs(2, 0.8)]
        # k=3, hits=2 → 2/3
        assert math.isclose(
            EvaluationService.precision_at_k(results, {1, 2}, 3), 2 / 3
        )


class TestNDCG:
    def test_perfect(self) -> None:
        results = [_rs(1, 1.0), _rs(2, 0.9)]
        # IDCG = 1/log2(2) + 1/log2(3) = 1 + 0.6309
        # DCG 同 → NDCG = 1
        ndcg = EvaluationService.ndcg_at_k(results, {1, 2}, 10)
        assert math.isclose(ndcg, 1.0, rel_tol=1e-6)

    def test_reverse(self) -> None:
        results = [_rs(99, 1.0), _rs(1, 0.9)]
        ndcg = EvaluationService.ndcg_at_k(results, {1}, 2)
        # IDCG = 1/log2(2) = 1
        # DCG  = 0 + 1/log2(3) = 0.6309
        assert math.isclose(ndcg, 0.6309, rel_tol=1e-3)

    def test_empty_ground_truth(self) -> None:
        ndcg = EvaluationService.ndcg_at_k([_rs(1, 1.0)], set(), 10)
        assert ndcg == 0.0


class TestMRR:
    def test_first_hit(self) -> None:
        results = [_rs(1, 1.0), _rs(2, 0.9)]
        assert EvaluationService.mrr(results, {1}) == 1.0

    def test_second_hit(self) -> None:
        results = [_rs(99, 1.0), _rs(1, 0.9)]
        assert EvaluationService.mrr(results, {1}) == 0.5

    def test_no_hit(self) -> None:
        results = [_rs(99, 1.0)]
        assert EvaluationService.mrr(results, {1}) == 0.0


class TestEvaluate:
    def test_full(self) -> None:
        svc = EvaluationService()
        results = [_rs(1, 1.0), _rs(2, 0.9), _rs(3, 0.8)]
        er = svc.evaluate(results, {1, 2}, k=3)
        assert er.hit_count == 2
        assert er.recall_at_k == 1.0
        assert math.isclose(er.precision_at_k, 2 / 3)
        assert er.ndcg_at_k > 0
        assert er.mrr == 1.0
        d = er.to_dict()
        assert d["k"] == 3
        assert d["hit_count"] == 2
