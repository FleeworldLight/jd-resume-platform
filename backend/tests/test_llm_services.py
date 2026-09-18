"""测试：Mock LLMService + 3 个 LLM 子服务。

两条路径都要覆盖：
* 真实 provider（provider_type != "mock"）→ 走 LLM
* mock provider（默认、离线）→ 走本地规则兜底
"""
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
    Suggestion,
    TailoredResume,
)
from app.schemas.resume_content import (
    ResumeBasics,
    ResumeContent,
    ResumeItem,
    ResumeProfile,
)
from app.services.customize_service import CustomizeService
from app.services.gap_analysis_service import GapAnalysisService
from app.services.llm_service import _build_mock_output
from app.services.predict_service import PredictService
from app.services.tailor_pipeline import tailored_to_text


def _make_llm(return_value, provider_type: str = "openai"):
    """构造一个假 LLMService。

    provider_type="openai" → 子服务走 LLM 分支（structured_invoke 被调用）
    provider_type="mock"   → 子服务走本地规则分支
    """
    llm = MagicMock()
    llm.structured_invoke = AsyncMock(return_value=return_value)
    provider = MagicMock()
    provider.provider_type = provider_type
    provider.name = provider_type
    llm.get_default_provider = AsyncMock(return_value=provider)
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


# ---------------- LLM 路径 ----------------


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

    assert out.match_score == 75
    assert out.extract_mode == "llm"
    llm.structured_invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_customize_service_returns_resume() -> None:
    """LLM 路径：产物是一份简历（content），且候选句必须被强制置为未确认。"""
    expected = TailoredResume(
        content=ResumeContent(
            basics=ResumeBasics(name="张三", phone="13800138000"),
            profile=ResumeProfile(
                title="Python 后端", summary="资深 Python 后端，3 年经验。"
            ),
            experiences=[
                ResumeItem(
                    title="后端工程师",
                    org="Acme",
                    role="核心开发",
                    start="2020-01",
                    end="2023-06",
                    description="负责订单服务",
                    highlights=["QPS 提升 3 倍"],
                    tech_stack=["Python", "Kafka"],
                )
            ],
            skills=["Python", "SQL"],
        ),
        target_position="Python 后端",
        # 故意让模型把候选句标成「已确认」——服务层必须强制改回未确认
        suggestions=[
            Suggestion(id="s01", skill="K8s", text="引入 K8s", confirmed=True)
        ],
    )
    llm = _make_llm(expected)
    svc = CustomizeService(llm)
    gap = GapReport(match_score=80)

    out = await svc.customize(_make_jd(), _make_resume(), gap)

    assert out.content.profile.summary.startswith("资深")
    assert out.content.basics.name == "张三"
    assert len(out.content.experiences) == 1
    assert out.content.experiences[0].highlights == ["QPS 提升 3 倍"]
    assert out.extract_mode == "llm"
    # 诚实兜底：模型无论如何标注，候选句都不能算「已确认」
    assert out.suggestions and all(not s.confirmed for s in out.suggestions)


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
    customized = TailoredResume(
        content=ResumeContent(
            profile=ResumeProfile(title="后端", summary="3 年 Python 经验"),
            skills=["Python"],
        ),
        target_position="Python 后端",
    )

    out = await svc.predict(_make_jd(), customized, question_count=3)
    assert out.questions[0].difficulty == "HARD"
    assert out.extract_mode == "llm"


# ---------------- mock 路径（本地规则兜底） ----------------


@pytest.mark.asyncio
async def test_gap_analysis_uses_rules_when_mock() -> None:
    """mock 下不再返回占位值，而是真的做技能集合比对。"""
    llm = _make_llm(None, provider_type="mock")
    svc = GapAnalysisService(llm)

    out = await svc.analyze(_make_jd(), _make_resume())

    assert out.extract_mode == "heuristic"
    assert "Python" in out.matched_skills          # JD 与简历都有
    assert [m.skill for m in out.missing_skills] == ["Kafka"]  # JD 有、简历没有
    assert out.match_score == 50                   # 1/2 覆盖
    llm.structured_invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_customize_uses_rules_when_mock_and_invents_nothing() -> None:
    """mock 路径：产物是一份简历；JD 要求而简历没有的只能变成未确认候选句。"""
    llm = _make_llm(None, provider_type="mock")
    svc = CustomizeService(llm)
    gap = GapReport(
        match_score=50,
        matched_skills=["Python"],
        missing_skills=[MissingSkill(skill="Kafka", priority="HIGH", reason="JD 要求")],
    )

    out = await svc.customize(_make_jd(), _make_resume(), gap)

    assert out.extract_mode == "heuristic"
    assert "Python" in out.content.skills
    # 简历文本里没有带时间段的经历块 → 不能凭空造经历
    assert out.content.experiences == []
    # JD 要 Kafka 但简历没写 → 只能进候选句，且默认未确认
    assert [s.skill for s in out.suggestions] == ["Kafka"]
    assert all(not s.confirmed for s in out.suggestions)
    # 最硬的一条：导出「已确认内容」时，未证实的 Kafka 绝不能出现在简历里
    assert "Kafka" not in tailored_to_text(out, include_unconfirmed=False)
    assert "Kafka" in tailored_to_text(out, include_unconfirmed=True)
    llm.structured_invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_predict_uses_rules_when_mock() -> None:
    llm = _make_llm(None, provider_type="mock")
    svc = PredictService(llm)
    gap = GapReport(
        match_score=50,
        matched_skills=["Python"],
        missing_skills=[MissingSkill(skill="Kafka", priority="HIGH", reason="JD 要求")],
    )

    out = await svc.predict(
        _make_jd(), CustomizedResume(summary="x"), question_count=2, gap=gap
    )

    assert out.extract_mode == "heuristic"
    assert 1 <= len(out.questions) <= 2
    assert out.questions[0].difficulty == "HARD"      # 缺失技能 → 高压追问
    assert "Kafka" in out.questions[0].question
    # STAR 必须是「让你自己填」的骨架，不能代写经历
    assert out.questions[0].star_answer.situation.startswith("（填")
    llm.structured_invoke.assert_not_awaited()


# ---------------- 回归：mock 占位值生成 ----------------


def test_build_mock_output_handles_required_fields() -> None:
    """回归：必填字段（无 default 且 default_factory 为 None）曾导致

    ``TypeError: 'NoneType' object is not callable`` ——
    即用户看到的「差距分析失败: 'NoneType' object is not callable」。
    """
    report = _build_mock_output(GapReport)
    assert report.match_score == 0
    assert report.matched_skills == []

    resume = _build_mock_output(CustomizedResume)
    assert isinstance(resume.summary, str)

    assert _build_mock_output(InterviewPrediction).questions == []
