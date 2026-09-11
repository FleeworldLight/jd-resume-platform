import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import type { Jd, JdStatus, PageResp } from "../types";
import { Card, ErrorBanner, StatusBadge } from "../components";
import { BriefcaseBusiness, ExternalLink, MapPin, RefreshCw, Search, Sparkles, Trash2 } from "lucide-react";

export default function Jds() {
  const [list, setList] = useState<PageResp<Jd> | null>(null);
  const [error, setError] = useState<unknown>(null);

  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [importing, setImporting] = useState(false);

  const pollingIds = useRef<Set<number>>(new Set());

  const reload = async () => {
    try {
      setList(await api.get<PageResp<Jd>>("/api/jds?page_size=50"));
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    reload();
  }, []);

  useEffect(() => {
    if (!list) return;
    const pending = list.items.filter(
      (j) =>
        j.crawl_status === "PENDING" ||
        j.crawl_status === "PROCESSING" ||
        j.crawl_status === "PARSED",
    );
    if (pending.length === 0) return;
    const timer = setInterval(async () => {
      for (const j of pending) {
        if (pollingIds.current.has(j.id)) continue;
        pollingIds.current.add(j.id);
        try {
          const s = await api.get<JdStatus>(`/api/jds/${j.id}/status`);
          if (
            s.crawl_status === "COMPLETED" ||
            s.crawl_status === "FAILED"
          ) {
            reload();
            pollingIds.current.delete(j.id);
          }
        } catch {
          pollingIds.current.delete(j.id);
        }
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [list]);

  const submitText = async () => {
    if (text.length < 10) {
      setError(new ApiError(-2, "JD 文本至少 10 字符"));
      return;
    }
    setError(null);
    try {
      await api.post<Jd>("/api/jds/text", { text });
      setText("");
      reload();
    } catch (e) {
      setError(e);
    }
  };

  const submitUrl = async () => {
    if (url.length < 10) {
      setError(new ApiError(-2, "URL 太短"));
      return;
    }
    setError(null);
    try {
      await api.post<Jd>("/api/jds/url", { url });
      setUrl("");
      reload();
    } catch (e) {
      setError(e);
    }
  };

  const importNowcoder = async () => {
    setError(null);
    setImporting(true);
    try {
      await api.post<Jd[]>("/api/jds/import-nowcoder?limit=10");
      await reload();
    } catch (e) {
      setError(e);
    } finally {
      setImporting(false);
    }
  };

  const onDelete = async (id: number) => {
    if (!confirm(`删除 JD ${id}?`)) return;
    try {
      await api.del(`/api/jds/${id}`);
      reload();
    } catch (e) {
      setError(e);
    }
  };

  return (
    <div className="space-y-6">
      <ErrorBanner error={error} />

      <section className="rounded-3xl bg-[#e4f4ef] border border-brand-100 p-6 sm:p-8 flex flex-col lg:flex-row lg:items-end gap-6">
        <div className="flex-1"><p className="eyebrow">NOWCODER CAMPUS</p><h1 className="text-3xl font-bold tracking-tight text-slate-900 mb-2">校招职位</h1><p className="text-slate-600 max-w-xl">实时抓取牛客校招岗位，像浏览职位市场一样筛选和查看，抓到的 JD 会直接进入你的工作台。</p></div>
        <button className="btn-primary shrink-0" onClick={importNowcoder} disabled={importing}><RefreshCw size={17} className={importing ? "animate-spin" : ""} />{importing ? "正在抓取职位…" : "抓取牛客校招"}</button>
      </section>

      <div className="grid lg:grid-cols-[minmax(0,1fr)_330px] gap-6 items-start">
      <section className="space-y-4">
        <div className="flex items-center justify-between"><div><p className="eyebrow">JOB FEED</p><h2 className="text-xl font-bold">推荐职位 <span className="text-slate-400 font-normal text-base">{list?.total ?? 0}</span></h2></div><button className="btn-ghost text-sm" onClick={reload}><RefreshCw size={15} />刷新</button></div>
        {!list && <div className="card text-sm text-gray-500">加载中…</div>}
        {list && list.items.length === 0 && <div className="card text-center py-14"><BriefcaseBusiness className="mx-auto text-brand-500 mb-3" size={30} /><p className="font-semibold">还没有职位</p><p className="text-sm text-slate-500 mt-1">点击“抓取牛客校招”导入真实岗位。</p></div>}
        {list?.items.map((j) => <JobCard key={j.id} job={j} onDelete={onDelete} />)}
      </section>

      <aside className="space-y-4 lg:sticky lg:top-24">
      <Card title="添加职位">
        <div className="space-y-4">
          <div>
            <label className="label">方式 1：粘贴文本</label>
            <textarea
              className="input min-h-[120px]"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="把 JD 文本粘到这里…"
            />
            <button
              className="btn-primary mt-2"
              onClick={submitText}
              disabled={text.length < 10}
            >
              <Sparkles size={16} />结构化抽取
            </button>
          </div>
          <div>
            <label className="label">方式 2：提交 URL（仅支持 牛客 / Boss）</label>
            <input
              className="input"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.nowcoder.com/jobs/detail/123"
            />
            <button
              className="btn-primary mt-2"
              onClick={submitUrl}
              disabled={url.length < 10}
            >
              <Search size={16} />抓取并解析
            </button>
          </div>
        </div>
      </Card>
      <div className="card bg-slate-900 text-white border-slate-800"><p className="text-xs font-bold tracking-widest text-brand-300 mb-2">TIP</p><p className="text-sm text-slate-300 leading-6">从牛客职位详情页复制链接，也可以单独抓取一个目标岗位。</p></div>
      </aside></div>
    </div>
  );
}

function JobCard({ job, onDelete }: { job: Jd; onDelete: (id: number) => void }) {
  const title = job.position || "待解析职位";
  const company = job.company || (job.source === "NOWCODER" ? "牛客校招岗位" : "未识别公司");
  return <article className="card hover:border-brand-400 transition group">
    <div className="flex gap-4"><div className="w-12 h-12 rounded-xl bg-brand-50 text-brand-600 grid place-items-center shrink-0"><BriefcaseBusiness size={22} /></div><div className="min-w-0 flex-1"><div className="flex items-start justify-between gap-3"><div><h3 className="font-bold text-lg text-slate-900 truncate">{title}</h3><p className="text-sm text-slate-500 mt-1">{company}</p></div><StatusBadge status={job.crawl_status} /></div><div className="flex flex-wrap gap-x-4 gap-y-2 mt-4 text-sm text-slate-500"><span className="inline-flex items-center gap-1"><MapPin size={14} />{job.city || "全国"}</span><span>{job.education || "学历不限"}</span>{job.salary_min && job.salary_max ? <span className="text-brand-700 font-semibold">{job.salary_min}-{job.salary_max}K</span> : <span>校招岗位</span>}</div></div></div>
    <div className="flex justify-between items-center mt-5 pt-4 border-t"><span className="text-xs text-slate-400">{new Date(job.created_at).toLocaleDateString()} · {job.source}</span><div className="flex gap-2">{job.source_url && <a className="btn-ghost text-xs py-1.5" href={job.source_url} target="_blank" rel="noreferrer"><ExternalLink size={14} />查看原岗位</a>}<button className="btn-ghost text-xs py-1.5 text-red-500" onClick={() => onDelete(job.id)} title="删除"><Trash2 size={14} /></button></div></div>
  </article>;
}
