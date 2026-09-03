"""测试：Prompt 模板渲染。"""
from __future__ import annotations

from app.prompts.jd_extract_v1 import JD_EXTRACT_PROMPT_V1
from app.schemas.llm_output import JdStructured


def test_prompt_renders_with_jd_text() -> None:
    prompt = JD_EXTRACT_PROMPT_V1
    rendered = prompt.format_messages(jd_text="我们招 Python 后端，要求 3 年经验。")
    # 至少 2 条消息：system + human
    assert len(rendered) >= 2
    human_msg = rendered[-1]
    content = human_msg.content if hasattr(human_msg, "content") else str(human_msg)
    assert "Python 后端" in content


def test_jd_structured_defaults() -> None:
    s = JdStructured()
    assert s.company is None
    assert s.skills == []
    assert s.responsibilities == []


def test_jd_structured_full() -> None:
    s = JdStructured(
        company="Acme",
        position="Python",
        salary_min=20,
        salary_max=40,
        city="北京",
        experience="3年",
        education="本科",
        skills=["Python", "SQL"],
        responsibilities=["写代码"],
        requirements=["3年经验"],
    )
    assert s.company == "Acme"
    assert s.salary_min == 20
    assert len(s.skills) == 2
