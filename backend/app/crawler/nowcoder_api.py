"""牛客职位列表接口客户端。

牛客职位广场前端调用的是：

    POST https://www.nowcoder.com/np-api/u/job/square-search
    body: {"page": 1, "pageSize": 20, "recruitType": 1}
    -> {"code": 0, "data": {"totalCount": 200, "totalPage": 10, "datas": [...]}}

相比「每个职位开一次浏览器逐页抓 DOM」，走这个接口：

* `pageSize` 可到 100，1 次请求就能拿到 100 条
* 字段更全：薪资区间、薪资月数、城市、公司名、届别、行业、规模
* 对目标站点压力小得多

接口返回里混有**两种形态**，本模块都做了解析（实测 100 条中有 22 条属于形态 B）：

* 形态 A —— 牛客平台职位：`jobName` / `jobCity` / `salaryMin|salaryMax|salaryMonth` /
  `eduLevel` / `graduationYear` / `recommendInternCompany` / `ext`(JSON 字符串)
* 形态 B —— 企业官网闪投：`jobTitle` / `description`(HTML) / `salary`(文本如「薪资面议」) /
  `companyName` / `education`(中文) / `city` / `skills`

设计约束：只调用站点自身前端使用的公开接口，未做任何绕过风控的处理。
请保持低频访问，仅用于个人求职分析。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

SEARCH_URL = "https://www.nowcoder.com/np-api/u/job/square-search"
DETAIL_URL = "https://www.nowcoder.com/jobs/detail/{job_id}"

RECRUIT_TYPE_SCHOOL = 1
MAX_PAGE_SIZE = 100

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_TAG_RE = re.compile(r"<[^>]+>")
_SALARY_RE = re.compile(r"(\d+)\s*-\s*(\d+)\s*K", re.IGNORECASE)

# eduLevel 数字码 → 中文。仅收录**已通过详情页反查核实**的取值，
# 未知码一律留空，不做猜测。
#   0 -> 不限（jobId 464768）
#   5000 -> 本科（jobId 460167）
#   6000 -> 硕士（jobId 467183）
_EDU_LEVEL_MAP: dict[int, str] = {
    0: "不限",
    5000: "本科",
    6000: "硕士",
}


def _html_to_text(raw: str) -> str:
    """把形态 B 的 description HTML 转成纯文本。"""
    if not raw:
        return ""
    text = raw
    for br in ("<br/>", "<br />", "<br>"):
        text = text.replace(br, "\n")
    for end in ("</p>", "</div>", "</li>", "</h1>", "</h2>", "</h3>"):
        text = text.replace(end, "\n")
    text = _TAG_RE.sub("", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _parse_salary_text(text: str) -> tuple[int | None, int | None]:
    """从「15-25K」「薪资面议」这类文本里抠出薪资区间。"""
    match = _SALARY_RE.search(text or "")
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


@dataclass
class NowcoderJob:
    """归一化后的牛客职位。"""

    job_id: int
    url: str
    position: str | None = None
    company: str | None = None
    city: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_month: int | None = None
    education: str | None = None
    experience: str | None = None
    industry: str | None = None
    scale: str | None = None
    requirements: str = ""
    responsibilities: str = ""
    body: str = ""  # 形态 B：description 已是完整正文
    raw_text: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        """转成与 DOM 抓取路径一致的 metadata 结构。"""
        return {
            "position": self.position,
            "company": self.company,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "city": self.city,
            "education": self.education,
            "experience": self.experience,
        }


def build_raw_text(job: NowcoderJob) -> str:
    """把接口字段拼成人可读的 JD 原文。"""
    head: list[str] = [f"职位：{job.position or '-'}"]
    if job.company:
        head.append(f"公司：{job.company}")
    if job.city:
        head.append(f"城市：{job.city}")
    if job.salary_min is not None and job.salary_max is not None:
        month = f" * {job.salary_month}薪" if job.salary_month else ""
        head.append(f"薪资：{job.salary_min}-{job.salary_max}K{month}")
    if job.education:
        head.append(f"学历：{job.education}")
    if job.experience:
        head.append(f"届别：{job.experience}")
    if job.industry:
        head.append(f"行业：{job.industry}")

    parts = ["\n".join(head)]
    if job.body:
        parts.append(job.body.strip())
    else:
        if job.responsibilities:
            parts.append(f"岗位职责\n{job.responsibilities.strip()}")
        if job.requirements:
            parts.append(f"任职要求\n{job.requirements.strip()}")
    return "\n\n".join(parts).strip()


def _clean_salary(lo: Any, hi: Any) -> tuple[int | None, int | None]:
    """过滤接口用哨兵值表示的「薪资面议」。

    牛客对不公开薪资的职位会返回 salaryMin=0 / salaryMax=9999999，
    直接入库会得到「0-9999999K」这种假数据，这里统一转成 None。
    """
    if not isinstance(lo, int) or not isinstance(hi, int):
        return None, None
    if lo <= 0 or hi <= 0 or hi >= 9_999_999 or lo > hi:
        return None, None
    return lo, hi


def _parse_platform_job(data: dict[str, Any], job_id: Any) -> NowcoderJob:
    """形态 A：牛客平台职位。"""
    company_info = data.get("recommendInternCompany") or {}
    ext: dict[str, Any] = {}
    raw_ext = data.get("ext")
    if isinstance(raw_ext, str) and raw_ext.strip():
        try:
            ext = json.loads(raw_ext)
        except (ValueError, TypeError):
            logger.warning("nowcoder_api.ext_parse_failed", job_id=job_id)

    edu_level = data.get("eduLevel")
    education = _EDU_LEVEL_MAP.get(edu_level) if isinstance(edu_level, int) else None
    city_list = data.get("jobCityList") or []
    salary_min, salary_max = _clean_salary(data.get("salaryMin"), data.get("salaryMax"))

    job = NowcoderJob(
        job_id=int(job_id),
        url=DETAIL_URL.format(job_id=job_id),
        position=data.get("jobName"),
        company=company_info.get("companyName") or company_info.get("companyShortName"),
        city=data.get("jobCity") or (city_list[0] if city_list else None),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_month=data.get("salaryMonth"),
        education=education,
        experience=data.get("graduationYear"),
        industry=(company_info.get("industryTagNameList") or [None])[0],
        scale=company_info.get("personScales") or company_info.get("scaleTagName"),
        requirements=str(ext.get("requirements") or ""),
        responsibilities=str(ext.get("infos") or ""),
        extra={
            "shape": "platform",
            "company_id": data.get("companyId"),
            "recruit_type": data.get("recruitType"),
            "edu_level": edu_level,
            "salary_month": data.get("salaryMonth"),
            "career_job_id": data.get("careerJobId"),
            "deliver_end": data.get("deliverEnd"),
        },
    )
    job.raw_text = build_raw_text(job)
    return job


def _parse_official_job(data: dict[str, Any], job_id: Any) -> NowcoderJob:
    """形态 B：企业官网闪投职位（description 为 HTML）。"""
    body = _html_to_text(str(data.get("description") or ""))
    salary_min, salary_max = _parse_salary_text(str(data.get("salary") or ""))
    extra_info = data.get("extraInfo") or {}

    job = NowcoderJob(
        job_id=int(job_id),
        url=DETAIL_URL.format(job_id=job_id),
        position=data.get("jobTitle"),
        company=data.get("companyName"),
        city=data.get("city"),
        salary_min=salary_min,
        salary_max=salary_max,
        education=data.get("education"),
        experience=None,
        industry=data.get("industry"),
        scale=data.get("scale") or data.get("financing"),
        body=body,
        extra={
            "shape": "official",
            "inner_job_id": data.get("jobId"),
            "company_id": data.get("companyId"),
            "recruit_type": data.get("recruitType"),
            "channel": extra_info.get("positionChannel_var"),
            "platform": data.get("platform"),
            "education_text": data.get("education"),
            "salary_text": data.get("salary"),
            "skills": data.get("skills"),
        },
    )
    job.raw_text = build_raw_text(job)
    return job


def parse_job(item: dict[str, Any]) -> NowcoderJob | None:
    """把接口返回的一条 raw item 解析成 NowcoderJob（兼容两种形态）。"""
    data = item.get("data") if isinstance(item.get("data"), dict) else item
    job_id = data.get("id")
    if job_id is None:
        return None
    try:
        if data.get("jobName") is not None:
            return _parse_platform_job(data, job_id)
        return _parse_official_job(data, job_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("nowcoder_api.parse_failed", job_id=job_id, error=str(exc))
        return None


class NowcoderApiClient:
    """牛客职位广场接口客户端。"""

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self._headers = {
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.nowcoder.com/jobs/school/jobs",
            "Origin": "https://www.nowcoder.com",
        }

    async def search(
        self,
        page: int = 1,
        page_size: int = MAX_PAGE_SIZE,
        recruit_type: int = RECRUIT_TYPE_SCHOOL,
    ) -> dict[str, Any]:
        """调用一次列表接口，返回 data 段。"""
        body = {
            "page": page,
            "pageSize": min(page_size, MAX_PAGE_SIZE),
            "recruitType": recruit_type,
        }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.post(SEARCH_URL, json=body, headers=self._headers)
            resp.raise_for_status()
            payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(
                f"牛客接口返回异常: code={payload.get('code')} msg={payload.get('msg')}"
            )
        return payload.get("data") or {}

    async def fetch_jobs(
        self,
        limit: int = 100,
        recruit_type: int = RECRUIT_TYPE_SCHOOL,
        page_size: int = MAX_PAGE_SIZE,
        on_page: Any = None,
    ) -> list[NowcoderJob]:
        """按需翻页抓取，直到达到 limit 或没有更多数据。"""
        jobs: list[NowcoderJob] = []
        seen: set[int] = set()
        page = 1
        while len(jobs) < limit:
            data = await self.search(page=page, page_size=page_size, recruit_type=recruit_type)
            items = data.get("datas") or []
            if not items:
                break
            for item in items:
                job = parse_job(item)
                if job is None or job.job_id in seen:
                    continue
                seen.add(job.job_id)
                jobs.append(job)
                if len(jobs) >= limit:
                    break
            if on_page:
                on_page(page, len(jobs), data.get("totalCount"), data.get("totalPage"))
            if page >= int(data.get("totalPage") or 1):
                break
            page += 1
        return jobs[:limit]
