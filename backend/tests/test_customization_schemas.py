"""测试：定制化 Pydantic Schema。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.customization import (
    CustomizedResume,
    Education,
    Experience,
    GapReport,
    InterviewPrediction,
    MissingSkill,
    PredictedQuestion,
    StarAnswer,
)


def test_gap_report_full() -> None:
    g = GapReport(
        match_score=80,
        matched_skills=["Python", "SQL"],
        missing_skills=[
            MissingSkill(skill="Kafka", priority="HIGH", reason="JD 强需求")
        ],
        experience_gaps=[],
        recommended_focus=["补 Kafka"],
    )
    assert g.match_score == 80
    assert g.missing_skills[0].priority == "HIGH"


def test_gap_report_score_out_of_range() -> None:
    with pytest.raises(ValidationError):
        GapReport(match_score=150)


def test_missing_skill_priority_enum() -> None:
    with pytest.raises(ValidationError):
        MissingSkill(skill="X", priority="CRITICAL", reason="r")


def test_customized_resume() -> None:
    r = CustomizedResume(
        summary="资深 Python 后端",
        skills=["Python", "Django"],
        experiences=[
            Experience(
                title="后端",
                company="Acme",
                duration="2020-2024",
                description="做后端",
                achievements=["优化 30%"],
                tech_stack=["Python"],
            )
        ],
        education=[Education(school="某大", major="CS", degree="本科", duration="2016-2020")],
        highlights=["高并发"],
    )
    assert r.experiences[0].achievements == ["优化 30%"]


def test_interview_prediction() -> None:
    q = PredictedQuestion(
        category="技术深度",
        difficulty="MEDIUM",
        question="如何保证消息不丢？",
        star_answer=StarAnswer(situation="S", task="T", action="A", result="R"),
        key_points=["ACK", "幂等"],
        hit_reason="简历有 Kafka 经验",
    )
    p = InterviewPrediction(questions=[q])
    assert p.questions[0].difficulty == "MEDIUM"
