"""技能分类表：把技能归到类别，用于简历里的「技能」分组展示。

为什么需要
----------
``heuristic_extract.SKILLS`` 是一维词典，命中后只能得到一串扁平的技能名。
但一份真实简历的「技能」区通常按类别分组（编程语言 / 后端 / 大数据 / …），
而且**组内顺序应该体现与目标岗位的相关度**——这是定制化最直接的增量价值。

设计约束
--------
本表**只用于展示层分组与去重**，不参与 ``analyze_gap`` 的命中判定，
以免改变既有匹配分数、引入回归。别名（K8s / Kubernetes）在这里归并，
避免同一技能以两种写法重复出现。
"""
from __future__ import annotations

from app.services.heuristic_extract import SKILLS

# 类别 → 技能。顺序即输出顺序（越靠前越像「硬技能」）。
SKILL_CATEGORIES: dict[str, tuple[str, ...]] = {
    "编程语言": (
        "Python", "Java", "JavaScript", "TypeScript", "Go 语言", "Golang",
        "C++", "C#", "Rust", "PHP", "Kotlin", "Swift", "Scala", "Ruby",
        "Shell", "SQL", "MATLAB",
    ),
    "后端 / 框架": (
        "Spring", "Spring Boot", "SpringCloud", "MyBatis", "FastAPI",
        "Django", "Flask", "Node.js", "Express", "gRPC", "RESTful",
    ),
    "架构能力": ("微服务", "分布式", "高并发"),
    "前端": (
        "Vue", "React", "Angular", "Next.js", "Vite", "Webpack", "HTML", "CSS",
    ),
    "数据库 / 存储": (
        "MySQL", "PostgreSQL", "Redis", "MongoDB", "Elasticsearch",
    ),
    "消息队列": ("Kafka", "RabbitMQ"),
    "大数据": (
        "Hadoop", "Hive", "Spark", "Flink", "HBase", "ClickHouse", "Doris", "ETL",
    ),
    "算法 / AI": (
        "机器学习", "深度学习", "PyTorch", "TensorFlow", "Transformer",
        "大模型", "LLM", "NLP", "计算机视觉", "OpenCV", "推荐系统",
        "强化学习", "RAG", "LangChain",
    ),
    "运维 / 工程化": (
        "Docker", "Kubernetes", "K8s", "Linux", "Git", "CI/CD", "Jenkins",
        "Nginx", "Prometheus", "Grafana",
    ),
    "云平台": ("阿里云", "AWS", "腾讯云", "Azure"),
    "移动 / 客户端 / 硬件": (
        "Android", "iOS", "Flutter", "Unity", "UE", "FFmpeg", "FPGA", "Verilog",
    ),
}

CATEGORY_ORDER: tuple[str, ...] = tuple(SKILL_CATEGORIES.keys())

# 同一技能的多种写法 → 统一写法（展示层去重）
_ALIAS: dict[str, str] = {
    "K8s": "Kubernetes",
    "Go 语言": "Golang",
    "SpringCloud": "Spring Cloud",
}

# 反向索引：技能 → 类别
_SKILL_TO_CATEGORY: dict[str, str] = {
    skill: cat for cat, skills in SKILL_CATEGORIES.items() for skill in skills
}


def canonical(skill: str) -> str:
    """把技能名归一（K8s → Kubernetes）。"""
    return _ALIAS.get(skill, skill)


def category_of(skill: str) -> str:
    """技能所属类别；词表外的技能归入「其他」。"""
    if skill in _SKILL_TO_CATEGORY:
        return _SKILL_TO_CATEGORY[skill]
    return "其他"


def canonical_set(skills: list[str] | tuple[str, ...] | set[str]) -> set[str]:
    """归一后的集合，用于跨写法比对（JD 写 K8s、简历写 Kubernetes 也算命中）。"""
    return {canonical(s) for s in skills}


def group_skills(
    skills: list[str],
    priority: list[str] | None = None,
) -> list[tuple[str, list[str]]]:
    """把技能按类别分组，组内优先排 ``priority``（通常是 JD 命中的技能）。

    返回 ``[(类别, [技能, ...]), ...]``，空组会被丢弃；
    类别顺序按 :data:`CATEGORY_ORDER`，保证每次输出稳定可比。
    """
    prio = [canonical(s) for s in (priority or [])]
    buckets: dict[str, list[str]] = {}

    for raw in skills:
        name = canonical(raw)
        if not name:
            continue
        cat = category_of(name)
        items = buckets.setdefault(cat, [])
        if name not in items:
            items.append(name)

    for cat, items in buckets.items():
        # 命中 JD 的排前面，其余保持原有相对顺序
        items.sort(key=lambda s: (0 if s in prio else 1, prio.index(s) if s in prio else 0))

    ordered: list[tuple[str, list[str]]] = []
    for cat in CATEGORY_ORDER:
        if buckets.get(cat):
            ordered.append((cat, buckets[cat]))
    if buckets.get("其他"):
        ordered.append(("其他", buckets["其他"]))
    return ordered


def is_known_skill(skill: str) -> bool:
    """是否在词典内（用于过滤 JD 里抽出来的噪声词）。"""
    return skill in _SKILL_TO_CATEGORY or skill in SKILLS
