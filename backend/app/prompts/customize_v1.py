"""定制简历 Prompt（v1）。

产物形态：**一份可直接投递的简历**（``TailoredResume``），而不是分析报告。
差距分析 / 面试押题 / 召回指标由其它 service 负责，这里只产出简历本体。

⚠️ 历史教训：旧版 prompt 里有一句「项目描述增加量化数据和与 JD 相关的关键词」，
那等于**鼓励模型编造数字**（凭空写「性能提升 40%」）。已删除。
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

CUSTOMIZE_PROMPT_V1 = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "你是一位资深简历顾问。请把用户简历改写成**一份可直接投递的简历**，"
                "使其对准目标岗位。\n\n"
                "输出结构（TailoredResume）：\n"
                "- content：简历本体，沿用原简历已有的结构，"
                "含 basics（姓名/电话/邮箱/城市/年龄/链接）、profile（求职岗位/附加身份/个人简介）、"
                "education、experiences（团队项目/实习/工作）、projects（个人项目）、skills；\n"
                "- target_position：目标岗位名（取自 JD）；\n"
                "- skill_groups：技能按类别分组，**组内按与 JD 的相关度排序**；\n"
                "- ranking：每条经历/项目与 JD 的相关度（0-100）及命中的 JD 技能；\n"
                "- suggestions：**岗位要求、但简历里没有任何依据**的内容，"
                "写成候选句，全部 confirmed=false；\n"
                "- tailor_notes：你做了哪些调整（供用户逐条核查）。\n\n"
                "红线（违反即视为失败）：\n"
                "1. **不得新增任何经历、项目、技能、奖项、证书**；\n"
                "2. **不得新增或修改任何数字**（人数、百分比、数据量、QPS、时间…），"
                "只能沿用原简历里已经写出的数字；\n"
                "3. 允许：调整顺序、合并同类信息、改写措辞、把原简历里已提到但没突出的事实写清楚；\n"
                "4. 缺失项只能进 suggestions，措辞必须是「示例句式，请替换成你的真实做法」的口吻，"
                "**不得直接断言用户做过**；\n"
                "5. 语言与原文保持一致（中文简历保持中文）。\n\n"
                "输出严格的 JSON。"
            ),
        ),
        (
            "human",
            (
                "JD：\n"
                "```\n"
                "{jd_text}\n"
                "```\n\n"
                "原简历：\n"
                "```\n"
                "{resume_text}\n"
                "```\n\n"
                "差距报告：\n"
                "{gap_report}\n\n"
                "请输出定制简历 JSON。"
            ),
        ),
    ]
)
