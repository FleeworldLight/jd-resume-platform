"""测试：Mock LLMService + 3 个 LLM 子服务。"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.jd import Jd
from app.db.models.resume import Resume
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
from app.services.customize_service import CustomizeService
from app.services.gap_analysis_service import GapAnalysisService
from app.services.predict_service import PredictService


def _make_llm(return_value):
    llm = MagicMock()
    llm.structured_invoke = AsyncMock(return_value=return_value)
    return llm


def _make_jd() -> Jd:
    jd = Jd(
        source="MANUAL",
        raw_text="我们招 Python 后端，要求 Kafka、3 年经验。",
        structured={
            "skills": ["Python", "Kafka"],
            "experience": "3年",
        },
        crawl_status="COMPLETED",
    )
    jd.id = 1
    jd.created_at = datetime.utcnow()
    jd.updated_at = datetime.utcnow()
    return jd


def _make_resume() -> Resume:
    r = Resume(
        original_filename="me.pdf",
        content_hash="abc",
        resume_text="张三，3 年 Python 经验，做过后端。",
        parse_status="COMPLETED",
    )
    r.id = 1
    r.created_at = datetime.utcnow()
    r.updated_at = datetime.utcnow()
    return r


@pytest.mark.asyncio
async def test_gap_analysis_calls_llm_and_returns() -> None:
    expected = GapReport(
        match_score=75,
        matched_skills=["Python"],
        missing_skills=[
            MissingSkill(skill="Kafka", priority="HIGH", reason="JD 要求")
        ],
    )
    llm = _make_llm(expected)
    svc = GapAnalysisService(llm)

    out = await svc.analyze(_make_jd(), _make_resume())

    assert out is expected
    assert out.match_score == 75
    llm.structured_invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_customize_service_returns_resume() -> None:
    expected = CustomizedResume(
        summary="资深 Python 后端，3 年经验。",
        skills=["Python", "SQL"],
        experiences=[
            Experience(
                title="后端工程师",
                company="Acme",
                duration="2020-2023",
                description="做后端",
            )
        ],
        education=[Education(school="X", major="CS", degree="本科", duration="2016-2020")],
    )
    llm = _make_llm(expected)
    svc = CustomizeService(llm)
    gap = GapReport(match_score=80)

    out = await svc.customize(_make_jd(), _make_resume(), gap)
    assert out.summary.startswith("资深")
    assert len(out.experiences) == 1


@pytest.mark.asyncio
async def test_predict_service_returns_questions() -> None:
    expected = InterviewPrediction(
        questions=[
            PredictedQuestion(
                category="技术深度",
                difficulty="HARD",
                question="如何保证 Kafka 不丢消息？",
                star_answer=StarAnswer(situation="S", task="T", action="A", result="R"),
                hit_reason="JD 要求",
            )
        ]
    )
    llm = _make_llm(expected)
    svc = PredictService(llm)
    customized = CustomizedResume(summary="x", skills=["Python"])

    out = await svc.predict(_make_jd(), customized, question_count=3)
    assert out.questions[0].difficulty == "HARD"
