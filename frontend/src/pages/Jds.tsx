import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import type { Jd, JdCrawlSummary, JdFacets, JdStatus, PageResp } from "../types";
import { Card, ErrorBanner, PageHero, StatusBadge } from "../components";
import {
  BriefcaseBusiness, Building2, ChevronLeft, ChevronRight, ExternalLink,
  Filter, GraduationCap, MapPin, RefreshCw, RotateCcw, Search, Sparkles,
  Trash2, X,
} from "lucide-react";

const PAGE_SIZE_OPTIONS = [12, 24, 48];

const SORT_OPTIONS = [
  { value: "latest", label: "最新入库" },
  { value: "salary_desc", label: "薪资 高→低" },
  { value: "salary_asc", label: "薪资 低→高" },
  { value: "company", label: "按公司名" },
  { value: "oldest", label: "最早入库" },
];

const EMPTY_QUERY = {
  page: 1,
  page_size: 12,
  keyword: "",
  city: "",
  education: "",
  source: "",
  salary_only: false,
  sort: "latest",
  salary_min: null as number | null,
  salary_max: null as number | null,
};

/** 读取 structured.crawl_meta（接口抓取时写入的溯源信息）。 */
function meta(job: Jd): Record<string, unknown> {
  const s = job.structured;
  if (!s || typeof s !== "object") return {};
  const cm = (s as Record<string, unknown>).crawl_meta;
  return cm && typeof cm === "object" ? (cm as Record<string, unknown>) : {};
}

/** 薪资展示：月薪用「K」，日薪等其它单位直接显示原始文本。 */
function salaryText(job: Jd): string {
  if (job.salary_min != null && job.salary_max != null) {
    const m = meta(job).salary_month;
    return `${job.salary_min}-${job.salary_max}K${typeof m === "number" && m > 0 ? ` · ${m}薪` : ""}`;
  }
  const d = meta(job).salary_display;
  return typeof d === "string" && d ? d : "薪资面议";
}

function hasSalary(job: Jd): boolean {
  return job.salary_min != null || typeof meta(job).salary_display === "string";
}

export default function Jds() {
  const [query, setQuery] = useState({ ...EMPTY_QUERY });
  const [keywordInput, setKeywordInput] = useState("");
  const [salaryRange, setSalaryRange] = useState("");

  const [list, setList] = useState<PageResp<Jd> | null>(null);
  const [facets, setFacets] = useState<JdFacets | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [crawling, setCrawling] = useState(false);
  const [detail, setDetail] = useState<Jd | null>(null);

  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // 关键词防抖：停止输入 350ms 后再查询
  useEffect(() => {
    if (keywordInput === query.keyword) return;
    const timer = setTimeout(
      () => setQuery((q) => ({ ...q, keyword: keywordInput, page: 1 })),
      350,
    );
    return () => clearTimeout(timer);
  }, [keywordInput, query.keyword]);

  const qs = useMemo(() => {
    const p = new URLSearchParams();
    p.set("page", String(query.page));
    p.set("page_size", String(query.page_size));
    if (query.keyword) p.set("keyword", query.keyword);
    if (query.city) p.set("city", query.city);
    if (query.education) p.set("education", query.education);
    if (query.source) p.set("source", query.source);
    if (query.sort) p.set("sort", query.sort);
    if (query.salary_only) p.set("salary_only", "true");
    if (query.salary_min != null) p.set("salary_min", String(query.salary_min));
    if (query.salary_max != null) p.set("salary_max", String(query.salary_max));
    return p.toString();
  }, [query]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [page, f] = await Promise.all([
        api.get<PageResp<Jd>>(`/api/jds?${qs}`),
        api.get<JdFacets>("/api/jds/facets"),
      ]);
      setList(page);
      setFacets(f);
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [qs]);

  useEffect(() => {
    void load();
  }, [load]);

  // 只在「抓取中」这类瞬态状态上轮询（PARSED 是终态，不需要轮询）
  const pending = useMemo(
    () =>
      (list?.items ?? []).filter(
        (j) => j.crawl_status === "PENDING" || j.crawl_status === "PROCESSING",
      ),
    [list],
  );

  useEffect(() => {
    if (pending.length === 0) return;
    const timer = setInterval(async () => {
      let finished = false;
      for (const j of pending) {
        try {
          const s = await api.get<JdStatus>(`/api/jds/${j.id}/status`);
          if (s.crawl_status === "COMPLETED" || s.crawl_status === "FAILED") finished = true;
        } catch {
          /* 忽略单次失败，下轮重试 */
        }
      }
      if (finished) void load();
    }, 3000);
    return () => clearInterval(timer);
  }, [pending, load]);

  const applyRange = (label: string) => {
    setSalaryRange(label);
    const item = facets?.salary_ranges.find((r) => r.value === label);
    setQuery((q) => ({
      ...q,
      page: 1,
      salary_min: item?.min ?? null,
      salary_max: item?.max ?? null,
    }));
  };

  const resetFilters = () => {
    setQuery({ ...EMPTY_QUERY });
    setKeywordInput("");
    setSalaryRange("");
  };

  const crawlNowcoder = async () => {
    setCrawling(true);
    setError(null);
    setNotice("");
    try {
      const kw = keywordInput.trim();
      const extra = kw ? `&keyword=${encodeURIComponent(kw)}` : "";
      const r = await api.post<JdCrawlSummary>(`/api/jds/crawl-nowcoder?limit=60${extra}`);
      setNotice(`${r.message}（库内共 ${r.total} 条）`);
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setCrawling(false);
    }
  };

  const reparse = async (id: number) => {
    setBusyId(id);
    setError(null);
    setNotice("");
    try {
      const updated = await api.post<Jd>(`/api/jds/${id}/reparse`);
      setDetail(updated);
      setNotice(`#${id} 已重新解析`);
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusyId(null);
    }
  };

  const onDelete = async (id: number) => {
    if (!confirm(`确认删除岗位 #${id}？该操作不可撤销。`)) return;
    setBusyId(id);
    try {
      await api.del(`/api/jds/${id}`);
      if (detail?.id === id) setDetail(null);
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusyId(null);
    }
  };

  const submitText = async () => {
    if (text.trim().length < 10) {
      setError(new ApiError(-2, "JD 文本至少 10 字符"));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.post<Jd>("/api/jds/text", { text });
      setText("");
      setNotice("已粘贴并完成结构化");
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setSubmitting(false);
    }
  };

  const submitUrl = async () => {
    if (url.trim().length < 10) {
      setError(new ApiError(-2, "URL 太短"));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.post<Jd>("/api/jds/url", { url: url.trim() });
      setUrl("");
      setNotice("已提交并抓取");
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setSubmitting(false);
    }
  };

  const total = list?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / query.page_size));
  const filtersActive =
    !!query.keyword || !!query.city || !!query.education || !!query.source || query.salary_only ||
    !!salaryRange;

  return (
    <div className="space-y-6">
      <ErrorBanner error={error} />

      <PageHero eyebrow="OPEN POSITIONS" title="在招岗位" desc="抓取或粘贴岗位，按关键词 / 城市 / 学历 / 薪资筛选，快速找到值得投递的机会。">
        <div className="flex flex-col items-start lg:items-end gap-3">
          {facets && (
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-600">
              <span>共 <b className="text-slate-900">{facets.total}</b> 条岗位</span>
              <span><b className="text-slate-900">{facets.with_salary}</b> 条有薪资</span>
              <span><b className="text-slate-900">{facets.companies}</b> 家公司</span>
            </div>
          )}
          <button className="btn-primary" onClick={crawlNowcoder} disabled={crawling}>
            <RefreshCw size={17} className={crawling ? "animate-spin" : ""} />
            {crawling ? "正在抓取…" : "抓取最新岗位"}
          </button>
        </div>
      </PageHero>

      {notice && (
        <div className="card border-brand-200 bg-brand-50/70 text-brand-800 text-sm py-3">
          {notice}
        </div>
      )}

      {/* ---------------- 筛选栏 ---------------- */}
      <section className="card space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 font-semibold text-slate-800">
            <Filter size={16} /> 筛选
          </div>
          {filtersActive && (
            <button className="btn-ghost text-xs" onClick={resetFilters}>
              <RotateCcw size={13} /> 重置
            </button>
          )}
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="sm:col-span-2">
            <label className="label">关键词</label>
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                className="input pl-9"
                value={keywordInput}
                onChange={(e) => setKeywordInput(e.target.value)}
                placeholder="岗位名 / 公司 / 城市，如：算法、华为、杭州"
              />
            </div>
          </div>

          <div>
            <label className="label">城市</label>
            <select
              className="input"
              value={query.city}
              onChange={(e) => setQuery((q) => ({ ...q, city: e.target.value, page: 1 }))}
            >
              <option value="">全部城市</option>
              {facets?.cities.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.value}（{c.count}）
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label">学历</label>
            <select
              className="input"
              value={query.education}
              onChange={(e) => setQuery((q) => ({ ...q, education: e.target.value, page: 1 }))}
            >
              <option value="">全部学历</option>
              {facets?.educations.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.value}（{c.count}）
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label">薪资区间</label>
            <select className="input" value={salaryRange} onChange={(e) => applyRange(e.target.value)}>
              <option value="">不限薪资</option>
              {facets?.salary_ranges.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.value}（{r.count}）
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label">来源</label>
            <select
              className="input"
              value={query.source}
              onChange={(e) => setQuery((q) => ({ ...q, source: e.target.value, page: 1 }))}
            >
              <option value="">全部来源</option>
              {facets?.sources.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.value}（{s.count}）
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label">排序</label>
            <select
              className="input"
              value={query.sort}
              onChange={(e) => setQuery((q) => ({ ...q, sort: e.target.value, page: 1 }))}
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-end">
            <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={query.salary_only}
                onChange={(e) =>
                  setQuery((q) => ({ ...q, salary_only: e.target.checked, page: 1 }))
                }
              />
              只看有薪资
            </label>
          </div>
        </div>
      </section>

      <div className="grid lg:grid-cols-[minmax(0,1fr)_330px] gap-6 items-start">
        {/* ---------------- 列表 ---------------- */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="eyebrow">JOB FEED</p>
              <h2 className="text-xl font-bold">
                岗位列表{" "}
                <span className="text-slate-400 font-normal text-base">
                  {total}
                  {loading ? " · 加载中…" : ""}
                </span>
              </h2>
            </div>
            <button className="btn-ghost text-sm" onClick={() => void load()}>
              <RefreshCw size={15} /> 刷新
            </button>
          </div>

          {!list && <div className="card text-sm text-gray-500">加载中…</div>}

          {list && list.items.length === 0 && (
            <div className="card text-center py-14">
              <BriefcaseBusiness className="mx-auto text-brand-500 mb-3" size={30} />
              <p className="font-semibold">
                {filtersActive ? "没有匹配的岗位" : "还没有岗位"}
              </p>
              <p className="text-sm text-slate-500 mt-1">
                {filtersActive
                  ? "换个关键词或放宽筛选条件试试。"
                  : "点右上角「抓取最新岗位」，或在右侧粘贴 JD 文本。"}
              </p>
              {filtersActive && (
                <button className="btn-ghost text-sm mt-3 mx-auto" onClick={resetFilters}>
                  <RotateCcw size={14} /> 重置筛选
                </button>
              )}
            </div>
          )}

          {list?.items.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              busy={busyId === job.id}
              onOpen={() => setDetail(job)}
              onDelete={() => onDelete(job.id)}
            />
          ))}

          {list && total > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <span className="text-sm text-slate-500">
                第 {query.page} / {totalPages} 页 · 共 {total} 条
              </span>
              <div className="flex items-center gap-2">
                <select
                  className="input py-1.5 text-sm"
                  value={query.page_size}
                  onChange={(e) =>
                    setQuery((q) => ({ ...q, page_size: Number(e.target.value), page: 1 }))
                  }
                >
                  {PAGE_SIZE_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      每页 {n} 条
                    </option>
                  ))}
                </select>
                <button
                  className="btn-ghost text-sm py-1.5"
                  disabled={query.page <= 1}
                  onClick={() => setQuery((q) => ({ ...q, page: Math.max(1, q.page - 1) }))}
                >
                  <ChevronLeft size={15} /> 上一页
                </button>
                <button
                  className="btn-ghost text-sm py-1.5"
                  disabled={query.page >= totalPages}
                  onClick={() =>
                    setQuery((q) => ({ ...q, page: Math.min(totalPages, q.page + 1) }))
                  }
                >
                  下一页 <ChevronRight size={15} />
                </button>
              </div>
            </div>
          )}
        </section>

        {/* ---------------- 侧栏 ---------------- */}
        <aside className="space-y-4 lg:sticky lg:top-24">
          <Card title="添加岗位">
            <div className="space-y-4">
              <div>
                <label className="label">方式 1：粘贴 JD 文本</label>
                <textarea
                  className="input min-h-[120px]"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="把 JD 文本粘到这里，会自动抽取职位 / 公司 / 城市 / 薪资 / 学历 / 技能…"
                />
                <button
                  className="btn-primary mt-2"
                  onClick={submitText}
                  disabled={text.length < 10 || submitting}
                >
                  <Sparkles size={16} /> 结构化抽取
                </button>
              </div>
              <div className="border-t pt-4">
                <label className="label">方式 2：提交职位 URL</label>
                <input
                  className="input"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.nowcoder.com/jobs/detail/123"
                />
                <button
                  className="btn-primary mt-2"
                  onClick={submitUrl}
                  disabled={url.length < 10 || submitting}
                >
                  <Search size={16} /> 抓取并解析
                </button>
              </div>
            </div>
          </Card>
          <div className="card bg-slate-900 text-white border-slate-800">
            <p className="text-xs font-bold tracking-widest text-brand-300 mb-2">TIP</p>
            <p className="text-sm text-slate-300 leading-6">
              顶部「抓取最新岗位」走牛客公开接口，几秒入库 60 条，并会带上当前关键词。
              需要几千条全量数据时，用命令行：
            </p>
            <pre className="mt-3 text-[11px] leading-5 bg-slate-800/80 rounded-lg p-3 overflow-x-auto text-slate-300">
{`backend\\.venv\\Scripts\\python.exe \\
  scripts\\crawl_jobs.py \\
  --source nowcoder \\
  --nowcoder-scope full --yes`}
            </pre>
          </div>
        </aside>
      </div>

      {detail && (
        <JobDetail
          job={detail}
          busy={busyId === detail.id}
          onClose={() => setDetail(null)}
          onReparse={() => reparse(detail.id)}
          onDelete={() => onDelete(detail.id)}
        />
      )}
    </div>
  );
}

/* ================= 岗位卡片 ================= */
function JobCard({
  job,
  busy,
  onOpen,
  onDelete,
}: {
  job: Jd;
  busy: boolean;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const title = job.position || "未命名岗位";
  const company = job.company || "未识别公司";
  const skills = (job.skills ?? []).slice(0, 5);
  return (
    <article className="card hover:border-brand-400 transition">
      <div className="flex gap-4">
        <div className="w-12 h-12 rounded-xl bg-brand-50 text-brand-600 grid place-items-center shrink-0">
          <BriefcaseBusiness size={22} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="font-bold text-lg text-slate-900 truncate">{title}</h3>
              <p className="text-sm text-slate-500 mt-0.5 flex items-center gap-1.5 truncate">
                <Building2 size={13} className="shrink-0" />
                {company}
              </p>
            </div>
            <StatusBadge status={job.crawl_status} />
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-3 text-sm text-slate-500">
            <span className="inline-flex items-center gap-1">
              <MapPin size={14} />
              {job.city || "城市未标注"}
            </span>
            <span className="inline-flex items-center gap-1">
              <GraduationCap size={14} />
              {job.education || "学历不限"}
            </span>
            {job.experience && <span>{job.experience}</span>}
            <span className={hasSalary(job) ? "text-brand-700 font-semibold" : "text-slate-400"}>
              {salaryText(job)}
            </span>
          </div>

          {skills.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {skills.map((s) => (
                <span
                  key={s}
                  className="text-[11px] px-2 py-0.5 rounded-md bg-slate-100 text-slate-600"
                >
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap justify-between items-center gap-2 mt-5 pt-4 border-t">
        <span className="text-xs text-slate-400">
          {new Date(job.created_at).toLocaleDateString()} · {job.source} · #{job.id}
        </span>
        <div className="flex gap-2">
          <button className="btn-ghost text-xs py-1.5" onClick={onOpen}>
            查看详情
          </button>
          {job.source_url && (
            <a
              className="btn-ghost text-xs py-1.5"
              href={job.source_url}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={14} /> 原岗位
            </a>
          )}
          <button
            className="btn-ghost text-xs py-1.5 text-red-500"
            onClick={onDelete}
            disabled={busy}
            title="删除"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
    </article>
  );
}

/* ================= 详情弹窗 ================= */
function JobDetail({
  job,
  busy,
  onClose,
  onReparse,
  onDelete,
}: {
  job: Jd;
  busy: boolean;
  onClose: () => void;
  onReparse: () => void;
  onDelete: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const m = meta(job);
  const extractMode =
    job.structured && typeof job.structured === "object"
      ? ((job.structured as Record<string, unknown>).extract_mode as string | undefined)
      : undefined;

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-start justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-3xl my-6 space-y-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-xl font-bold text-slate-900">{job.position || "未命名岗位"}</h2>
            <p className="text-sm text-slate-500 mt-1">
              {job.company || "未识别公司"} · #{job.id} · {job.source}
            </p>
          </div>
          <button className="btn-ghost p-2" onClick={onClose} title="关闭">
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Field label="城市" value={job.city || "-"} />
          <Field label="学历" value={job.education || "-"} />
          <Field label="经验 / 届别" value={job.experience || "-"} />
          <Field label="薪资" value={salaryText(job)} />
        </div>

        {(job.skills ?? []).length > 0 && (
          <div>
            <p className="label">技能标签</p>
            <div className="flex flex-wrap gap-1.5">
              {(job.skills ?? []).map((s) => (
                <span key={s} className="text-xs px-2 py-1 rounded-md bg-brand-50 text-brand-700">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        {(job.responsibilities ?? []).length > 0 && (
          <div>
            <p className="label">岗位职责</p>
            <ul className="text-sm text-slate-600 space-y-1.5 list-disc pl-5">
              {(job.responsibilities ?? []).map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        {(job.requirements ?? []).length > 0 && (
          <div>
            <p className="label">任职要求</p>
            <ul className="text-sm text-slate-600 space-y-1.5 list-disc pl-5">
              {(job.requirements ?? []).map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <p className="label">原始 JD 文本</p>
          <pre className="max-h-72 overflow-auto text-xs leading-6 whitespace-pre-wrap bg-slate-50 border rounded-xl p-3 text-slate-700">
            {job.raw_text || "（无）"}
          </pre>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t text-xs text-slate-400">
          <span>
            {extractMode ? `字段来源：${extractMode}` : ""}
            {typeof m.salary_unit === "string" ? ` · 薪资单位：${m.salary_unit}` : ""}
            {typeof m.via === "string" ? ` · 抓取入口：${m.via}` : ""}
          </span>
          <div className="flex gap-2">
            <button className="btn-ghost text-sm" onClick={onReparse} disabled={busy}>
              <RotateCcw size={14} className={busy ? "animate-spin" : ""} /> 重新解析
            </button>
            {job.source_url && (
              <a className="btn-ghost text-sm" href={job.source_url} target="_blank" rel="noreferrer">
                <ExternalLink size={14} /> 打开原岗位
              </a>
            )}
            <button
              className="btn-ghost text-sm text-red-500"
              onClick={onDelete}
              disabled={busy}
            >
              <Trash2 size={14} /> 删除
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-slate-50/70 px-3 py-2">
      <div className="text-[11px] text-slate-400">{label}</div>
      <div className="text-sm text-slate-800 truncate" title={value}>
        {value}
      </div>
    </div>
  );
}
