"""结构化简历解析/渲染的测试。

核心保证：
1. **往返稳定** —— `parse(render(c)) == c`，反复编辑保存不会逐次漂移
2. **不丢内容** —— 认不出的行进 extras、认不出的小节进 custom_sections，
   渲染时原样写回
"""
from __future__ import annotations

from app.services.resume_content_service import content_to_text, text_to_content

SAMPLE = """张三
求职岗位：后端开发实习 | 大三
22岁
Telephone：13800138000 | Email：zhangsan@example.com
代码
GitHub：https://github.com/example
个人文档
熟悉 Python 与分布式系统，做过两个完整项目。
• 电商系统 ― https://github.com/example/shop
学习经历
2022-09 ~ 2026-06 某某大学 计算机科学与技术
团队项目
2025-03 ~ 2025-06 数据库课程 核心开发
订单流水分析平台
基于 Flink 构建实时订单流水分析，支撑运营日报
• 设计 3 层数仓，查询耗时下降 60%
技术栈：Flink、Hive、Kafka
个人项目
2025-01 ~ 2025-03 个人博客系统 独立开发
基于 Next.js 的博客系统，支持 Markdown 渲染与全文搜索
• 实现增量静态生成，首屏 0.8s
技能
Python、SQL、Docker
奖项
校级一等奖学金
兴趣爱好
篮球、摄影
"""


def test_parse_extracts_all_sections() -> None:
    c = text_to_content(SAMPLE)
    assert c.basics.name == "张三"
    assert c.basics.phone == "13800138000"
    assert c.basics.email == "zhangsan@example.com"
    assert c.basics.age == "22岁"
    assert c.basics.links == ["GitHub：https://github.com/example"]
    assert c.profile.title == "后端开发实习"
    assert c.profile.tagline == "大三"
    assert "分布式系统" in c.profile.summary
    assert len(c.profile.highlights) == 1

    assert len(c.education) == 1
    assert c.education[0].school == "某某大学"
    assert c.education[0].major == "计算机科学与技术"
    assert c.education[0].start == "2022-09"

    assert len(c.experiences) == 1
    exp = c.experiences[0]
    assert exp.title == "订单流水分析平台"
    assert exp.org == "数据库课程"
    assert exp.role == "核心开发"
    assert "实时订单流水分析" in exp.description
    assert len(exp.highlights) == 1
    assert exp.tech_stack == ["Flink", "Hive", "Kafka"]

    assert len(c.projects) == 1
    # 个人项目没有独立标题行 → 标题留空，靠 org 展示
    assert c.projects[0].title == ""
    assert c.projects[0].org == "个人博客系统"
    assert "增量静态生成" in content_to_text(c) or "增量静态生成" in (
        c.projects[0].highlights[0] if c.projects[0].highlights else ""
    )

    assert c.skills == ["Python", "SQL", "Docker"]
    assert c.awards == ["校级一等奖学金"]
    # 未知小节被保留成自定义小节，而不是丢掉
    assert [s.title for s in c.custom_sections] == ["兴趣爱好"]
    assert c.custom_sections[0].lines == ["篮球、摄影"]
    assert c.extras == []


def test_round_trip_is_stable() -> None:
    c1 = text_to_content(SAMPLE)
    c2 = text_to_content(content_to_text(c1))
    assert c2.model_dump(exclude={"parse_note"}) == c1.model_dump(exclude={"parse_note"})

    # 连续保存两次也不漂移
    c3 = text_to_content(content_to_text(c2))
    assert c3.model_dump(exclude={"parse_note"}) == c1.model_dump(exclude={"parse_note"})


def test_round_trip_preserves_key_content() -> None:
    """渲染后的文本必须包含原文里的关键信息（手机/邮箱/学校/项目/要点/技能）。"""
    out = content_to_text(text_to_content(SAMPLE))
    for needle in [
        "张三",
        "13800138000",
        "zhangsan@example.com",
        "某某大学",
        "计算机科学与技术",
        "订单流水分析平台",
        "设计 3 层数仓，查询耗时下降 60%",
        "Flink、Hive、Kafka",
        "个人博客系统",
        "Python、SQL、Docker",
        "校级一等奖学金",
        "篮球、摄影",
    ]:
        assert needle in out, f"渲染结果里丢了：{needle}"


def test_unknown_lines_go_to_extras_not_dropped() -> None:
    """一小段认不出的内容必须出现在渲染结果里（不能静默丢弃）。"""
    text = "李四\n求职岗位：测试\n这一段是完全无法归类的内容 abcdefg\n"
    c = text_to_content(text)
    assert c.extras == ["这一段是完全无法归类的内容 abcdefg"]
    assert "abcdefg" in content_to_text(c)


def test_empty_and_whitespace_input() -> None:
    for text in ("", "   \n\n  "):
        c = text_to_content(text)
        assert c.basics.name == ""
        assert c.extras == []
        assert content_to_text(c).strip() == ""


def test_parse_note_reports_quality() -> None:
    clean = text_to_content(SAMPLE)
    assert "全部归类" in clean.parse_note

    messy = text_to_content(
        "王五\n求职岗位：测试\n"
        "这是一行很长很长的、认不出来的内容，长度超过十二个字所以只会进 extras 区。\n"
    )
    assert "未能自动归类" in messy.parse_note
