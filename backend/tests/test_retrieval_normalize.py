"""测试：召回分数归一化 + 混合。"""
from __future__ import annotations

from app.services.retrieval_service import ResumeScore, _normalize_scores


def test_normalize_empty() -> None:
    assert _normalize_scores([]) == []


def test_normalize_zero_max() -> None:
    scores = [ResumeScore(1, 0.0), ResumeScore(2, 0.0)]
    out = _normalize_scores(scores)
    assert all(s.score == 0.0 for s in out)


def test_normalize_basic() -> None:
    scores = [
        ResumeScore(1, 10.0),
        ResumeScore(2, 5.0),
        ResumeScore(3, 0.0),
    ]
    out = _normalize_scores(scores)
    assert out[0].score == 1.0
    assert out[1].score == 0.5
    assert out[2].score == 0.0


def test_normalize_preserves_ids() -> None:
    scores = [ResumeScore(42, 1.0), ResumeScore(7, 0.5)]
    out = _normalize_scores(scores)
    assert {s.resume_id for s in out} == {42, 7}
