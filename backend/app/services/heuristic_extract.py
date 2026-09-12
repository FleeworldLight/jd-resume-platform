"""规则式 JD 抽取（mock provider 下的兜底）。

背景
----
项目默认的 LLM provider 是 ``mock``（离线、不发任何外部请求）。mock 只按 schema
返回占位值，所以「粘贴 JD 文本 → 结构化抽取」在默认配置下会抽出一堆空字段，
看起来像"功能坏了"。

这里提供一套**纯规则**的抽取实现。当默认 provider 是 mock 时，
``JdService.structure_jd`` 会改走它，让「粘贴即抽取」在没有配置真实模型时也能用。

诚实声明：这不是 LLM，用的是正则 + 段落切分 + 词典匹配。结果会标记
``structured["extract_mode"] = "heuristic"``，与真实 LLM 结果区分开。
配置了真实 provider 后会自动切回 LLM 路径。
"""
from __future__ import annotations

import re

from app.schemas.llm_output import JdStructured

# ---------------- 词典 ----------------

CITIES: tuple[str, ...] = (
    "北京", "上海", "深圳", "广州", "杭州", "成都", "武汉", "南京", "西安", "苏州",
    "天津", "重庆", "长沙", "郑州", "青岛", "宁波", "东莞", "佛山", "合肥", "福州",
    "厦门", "济南", "大连", "沈阳", "哈尔滨", "长春", "石家庄", "太原", "南昌",
    "昆明", "贵阳", "南宁", "兰州", "乌鲁木齐", "呼和浩特", "珠海", "无锡", "常州",
    "温州", "嘉兴", "绍兴", "中山", "惠州", "烟台", "潍坊", "徐州", "泉州", "香港",
)

SKILLS: tuple[str, ...] = (
    # 语言
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Golang", "Go 语言",
    "Rust", "PHP", "Kotlin", "Swift", "Scala", "Ruby", "Shell", "SQL", "MATLAB",
    # 后端 / 框架
    "FastAPI", "Django", "Flask", "Spring", "Spring Boot", "SpringCloud", "MyBatis",
    "Node.js", "Express", "gRPC", "RESTful", "微服务", "分布式", "高并发",
    # 前端
    "React", "Vue", "Angular", "Next.js", "Webpack", "Vite", "HTML", "CSS",
    # 数据 / 存储
    "MySQL", "PostgreSQL", "Redis", "MongoDB", "Elasticsearch", "Kafka", "RabbitMQ",
    "Hive", "HBase", "ClickHouse", "Doris", "Flink", "Spark", "Hadoop", "ETL",
    # 算法 / AI
    "机器学习", "深度学习", "PyTorch", "TensorFlow", "Transformer", "大模型", "LLM",
    "NLP", "计算机视觉", "OpenCV", "推荐系统", "强化学习", "RAG", "LangChain",
    # 工程 / 运维
    "Docker", "Kubernetes", "K8s", "Linux", "Git", "CI/CD", "Jenkins", "Nginx",
    "Prometheus", "Grafana", "阿里云", "AWS", "腾讯云", "Azure",
    # 其它
    "Android", "iOS", "Flutter", "Unity", "UE", "FFmpeg", "FPGA", "Verilog",
)

# 段落标题 → 归类
_RESP_HEADINGS = (
    "岗位职责", "工作职责", "职位描述", "工作内容", "岗位描述", "职责描述",
    "您将", "你将", "主要职责", "工作职责", "岗位工作", "job description",
)
_REQ_HEADINGS = (
    "任职要求", "岗位要求", "任职资格", "岗位职责及要求", "职位要求", "招聘要求",
    "我们希望", "能力要求", "任职条件", "要求", "qualification",
)

_HEADING_RE = re.compile(
    r"^\s*(?:\d+[.、)]\s*|[一二三四五六七八九十]+[、.]\s*)?"
    r"([\u4e00-\u9fa5A-Za-z /]{2,12})\s*[:：]?\s*$"
)

_SALARY_KB_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*[kK]", re.IGNORECASE
)
_SALARY_WAN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*万")
_EDU_RE = re.compile(r"(博士|硕士|研究生|本科|大专|专科|统招本科|不限学历|学历不限)")
_EXP_RE = re.compile(
    r"(\d+\s*[-~]\s*\d+\s*年(?:以上)?(?:工作)?经验|应届(?:毕业生)?|"
    r"\d+\s*年以上(?:工作)?经验|经验不限|不限经验|实习)"
)
_LABELED = {
    "company": re.compile(r"(?:公司|企业|公司名称|单位)\s*[:：]\s*([^\s\n|，,]{2,40})"),
    "position": re.compile(r"(?:职位|岗位|职位名称|岗位名称|招聘职位)\s*[:：]\s*([^\n|，,]{2,50})"),
    "city": re.compile(r"(?:城市|工作地点|工作城市|所在地|地点)\s*[:：]\s*([^\s\n|，,]{2,20})"),
}

# 行首出现这些词，说明是段落标题而不是岗位名
_HEADING_LIKE = (
    "岗位描述", "职位描述", "工作职责", "岗位职责", "任职要求", "岗位要求",
    "招聘要求", "职位要求", "职位信息", "岗位信息", "主要职责", "工作内容",
    "您将", "你将", "您可以", "您需要", "您具备", "我们", "以下",
)
# 岗位名后面紧跟这些词 → 从这里截断
_TAIL_LABELS = re.compile(r"(公司|企业|城市|工作地点|薪资|待遇|学历|经验|岗位职责|任职要求)")


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines()]


def _clean_position(value: str | None) -> str | None:
    """岗位名清洗：截断掉粘连的「公司/城市/薪资」等后续字段。"""
    if not value:
        return None
    text = re.split(r"\s{2,}", value.strip(), maxsplit=1)[0]
    m = _TAIL_LABELS.search(text)
    if m and m.start() >= 2:
        text = text[: m.start()]
    text = text.strip(" 　:：-—|·")
    return text[:60] or None


def _first_meaningful(lines: list[str]) -> str | None:
    """取第一行有意义的短文本当作岗位名。

    跳过段落标题（"岗位描述"）、以冒号结尾的引导句（"您可以："）、
    以及带句读/过长的描述性句子——那些是正文，不是岗位名。
    """
    for ln in lines:
        clean = ln.strip(" 　:：-—|")
        if not (2 <= len(clean) <= 30):
            continue
        if clean.endswith(("：", ":", "；", ";", "。", "，", ",")):
            continue
        if any(ch in clean for ch in "。；"):
            continue
        if any(clean.startswith(w) for w in _HEADING_LIKE) or clean in _HEADING_LIKE:
            continue
        # 列表项（- / • / 1. / （1））不是岗位名
        if re.match(r"^[-•·●○*▪（(]?\s*\d*[.、)]", clean) or clean.startswith(("-", "•", "·", "*")):
            continue
        return _clean_position(clean)
    return None


def _extract_section(lines: list[str], headings: tuple[str, ...]) -> list[str]:
    """按小标题切出段落正文，返回条目列表。"""
    out: list[str] = []
    collecting = False
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            continue
        # 前 12 个字符里命中标题，就认为进入了这个段落
        head = stripped[:14]
        if any(h in head for h in headings):
            collecting = True
            # 标题后面同一行还有内容 → 也算正文
            rest = re.sub(
                r"^.*?(?:" + "|".join(re.escape(h) for h in headings) + r")\s*[:：]?\s*",
                "",
                stripped,
                count=1,
            ).strip()
            if rest and not rest.endswith(("：", ":")):
                out.append(rest)
            continue
        if collecting:
            # 遇到另一个段落标题就停止
            if any(h in head for h in _REQ_HEADINGS + _RESP_HEADINGS) and not any(
                h in head for h in headings
            ):
                break
            m = _HEADING_RE.match(stripped)
            if m and m.group(1).strip() in ("岗位职责", "任职要求", "岗位要求"):
                break
            # 去掉列表符号与序号，但不要把「2027届」这种年份吃掉
            cleaned = stripped
            cleaned = re.sub(r"^[-•·●○*▪]\s*", "", cleaned)
            cleaned = re.sub(r"^\d{1,2}\s*[.、)）]\s*", "", cleaned)
            cleaned = re.sub(r"^[、,，]\s*", "", cleaned)
            cleaned = cleaned.strip()
            # 丢掉「您可以：」「您具备以下条件：」这类引导句
            if not cleaned or cleaned.endswith(("：", ":")) or cleaned in headings:
                continue
            out.append(cleaned)
    return out


def _extract_skills(text: str) -> list[str]:
    found: list[str] = []
    for skill in SKILLS:
        # 用单词边界尽量精确匹配，避免 Go 命中 "Google"
        pattern = r"(?<![A-Za-z])" + re.escape(skill) + r"(?![A-Za-z])"
        if re.search(pattern, text, re.IGNORECASE):
            if skill not in found:
                found.append(skill)
    return found[:30]


def extract_jd_heuristic(text: str) -> JdStructured:
    """纯规则抽取 JD 字段。"""
    raw = text or ""
    lines = _lines(raw)

    position = None
    m = _LABELED["position"].search(raw)
    if m:
        position = _clean_position(m.group(1))
    if not position:
        position = _first_meaningful(lines)

    company = None
    m = _LABELED["company"].search(raw)
    if m:
        company = m.group(1).strip()
    else:
        m = re.search(
            r"([\u4e00-\u9fa5A-Za-z（）()]{2,30}"
            r"(?:有限公司|股份有限公司|集团|研究院|研究所|科技公司|事业部))",
            raw,
        )
        if m:
            company = m.group(1).strip()

    city = None
    m = _LABELED["city"].search(raw)
    if m:
        city = m.group(1).strip()
    if not city:
        for c in CITIES:
            if c in raw:
                city = c
                break

    salary_min = salary_max = None
    if not re.search(r"(元\s*/\s*天|元/天|日薪|按天)", raw):
        m = _SALARY_KB_RE.search(raw)
        if m:
            salary_min, salary_max = int(float(m.group(1))), int(float(m.group(2)))
        else:
            m = _SALARY_WAN_RE.search(raw)
            if m:
                salary_min = int(float(m.group(1)) * 10)
                salary_max = int(float(m.group(2)) * 10)

    edu = _EDU_RE.search(raw)
    education = edu.group(1) if edu else None
    if education == "学历不限":
        education = "不限"

    exp = _EXP_RE.search(raw)
    experience = exp.group(1).strip() if exp else None

    responsibilities = _extract_section(lines, _RESP_HEADINGS)
    requirements = _extract_section(lines, _REQ_HEADINGS)

    return JdStructured(
        company=company,
        position=position,
        salary_min=salary_min,
        salary_max=salary_max,
        city=city,
        experience=experience,
        education=education,
        skills=_extract_skills(raw),
        responsibilities=responsibilities[:20],
        requirements=requirements[:20],
    )
