import { useEffect, useState } from "react";
import { api } from "../api";
import type {
  Customization,
  CustomizationDetail,
  Jd,
  PageResp,
  Resume,
  TailorSuggestion,
  TailoredResume,
} from "../types";
import { Card, ErrorBanner, PageHero, StatusBadge } from "../components";

/** 可用于定制化的 JD 状态：PARSED 已抽好字段，COMPLETED 还多跑了一遍结构化 */
const USABLE_JD_STATUS = ["COMPLETED", "PARSED"];

const UNCONFIRMED_TAG = "〔未证实·待确认〕";

export default function Customizations() {
  const [list, setList] = useState<PageResp<Customization> | null>(null);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [error, setError] = useState<unknown>(null);

  // JD 选择器（4800+ 条，用关键词搜索而不是全量下拉）
  const [jdKeyword, setJdKeyword] = useState("");
  const [jdOptions, setJdOptions] = useState<Jd[]>([]);
  const [jdLoading, setJdLoading] = useState(false);
  const [selectedJd, setSelectedJd] = useState<Jd | null>(null);

  const [resumeId, setResumeId] = useState<number | "">("");
  const [count, setCount] = useState(5);
  const [submitting, setSubmitting] = useState(false);
  const [detail, setDetail] = useState<CustomizationDetail | null>(null);
  const [savingSuggestions, setSavingSuggestions] = useState(false);

  const reload = async () => {
    try {
      const [cs, r] = await Promise.all([
        api.get<PageResp<Customization>>("/api/customizations?page_size=50"),
        api.get<PageResp<Resume>>("/api/resumes?page_size=50"),
      ]);
      setList(cs);
      setResumes(r.items);
      if (!resumeId) {
        const ok = r.items.find((x) => x.parse_status === "COMPLETED");
        if (ok) setResumeId(ok.id);
      }
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // JD 关键词搜索（防抖）
  useEffect(() => {
    const timer = setTimeout(async () => {
      setJdLoading(true);
      try {
        const q = jdKeyword
          ? `&keyword=${encodeURIComponent(jdKeyword)}`
          : "";
        const r = await api.get<PageResp<Jd>>(`/api/jds?page_size=20&sort=latest${q}`);
        setJdOptions(r.items);
      } catch (e) {
        setError(e);
      } finally {
        setJdLoading(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [jdKeyword]);

  const submit = async () => {
    if (!selectedJd || !resumeId) {
      setError(new Error("请先选择岗位和简历"));
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const c = await api.post<Customization>("/api/customizations", {
        jd_id: selectedJd.id,
        base_resume_id: resumeId,
        question_count: count,
      });
      await reload();
      setDetail(await api.get<CustomizationDetail>(`/api/customizations/${c.id}`));
    } catch (e) {
      setError(e);
      await reload();
    } finally {
      setSubmitting(false);
    }
  };

  const showDetail = async (id: number) => {
    try {
      setDetail(await api.get<CustomizationDetail>(`/api/customizations/${id}`));
    } catch (e) {
      setError(e);
    }
  };

  const download = (id: number, kind: "resume-pdf" | "docx" | "report") => {
    const job =
      kind === "resume-pdf"
        ? api.downloadResumePdf(id)
        : kind === "docx"
          ? api.downloadResumeDocx(id)
          : api.downloadReportPdf(id);
    job.catch((e) => setError(e));
  };

  /** 逐条确认 / 驳回补足建议（ids 为 null 表示全部） */
  const applySuggestions = async (ids: string[] | null, confirmed: boolean) => {
    if (!detail) return;
    setSavingSuggestions(true);
    setError(null);
    try {
      const d = await api.post<CustomizationDetail>(
        `/api/customizations/${detail.id}/suggestions`,
        { ids, confirmed },
      );
      setDetail(d);
      await reload();
    } catch (e) {
      setError(e);
    } finally {
      setSavingSuggestions(false);
    }
  };

  const onDelete = async (id: number) => {
    if (!confirm(`删除定制化 ${id}?`)) return;
    try {
      await api.del(`/api/customizations/${id}`);
      if (detail?.id === id) setDetail(null);
      await reload();
    } catch (e) {
      setError(e);
    }
  };

  const onRetry = async (id: number) => {
    try {
      await api.post(`/api/customizations/${id}/retry`);
      await reload();
      setDetail(await api.get<CustomizationDetail>(`/api/customizations/${id}`));
    } catch (e) {
      setError(e);
      await reload();
    }
  };

  return (
    <div className="space-y-4">
      <ErrorBanner error={error} />

      <PageHero
        eyebrow="TAILORED APPLICATION"
        title="定制化"
        desc={
          <>
            选一条在招岗位 + 一份基础简历，产出一份<b>可直接投递的简历</b>：
            <b> 重排经历 → 归拢技能 → 标注差距</b>。
            岗位要求但你简历里没有依据的内容，只会变成<b>候选句</b>，
            经你逐条确认后才写进简历——不代你编造经历。
          </>
        }
      />

      <Card title="发起定制化">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* ---- JD 选择：搜索式 ---- */}
          <div>
            <label className="label">目标岗位（可搜索，共 4800+ 条）</label>
            <input
              className="input"
              value={jdKeyword}
              onChange={(e) => setJdKeyword(e.target.value)}
              placeholder="输入关键词，如：大数据、算法、华为"
            />
            {selectedJd && (
              <div className="mt-2 text-sm rounded-lg bg-brand-50 text-brand-800 px-3 py-2">
                已选：#{selectedJd.id} {selectedJd.position || "未命名岗位"} ·{" "}
                {selectedJd.company || "未识别公司"}
              </div>
            )}
            <div className="mt-2 border rounded-xl max-h-52 overflow-auto divide-y">
              {jdLoading && (
                <div className="px-3 py-2 text-sm text-slate-400">搜索中…</div>
              )}
              {!jdLoading && jdOptions.length === 0 && (
                <div className="px-3 py-2 text-sm text-slate-400">
                  没有匹配的岗位，换个关键词试试。
                </div>
              )}
              {jdOptions.map((j) => (
                <button
                  key={j.id}
                  type="button"
                  onClick={() => setSelectedJd(j)}
                  className={`w-full text-left px-3 py-2 hover:bg-slate-50 transition ${
                    selectedJd?.id === j.id ? "bg-brand-50" : ""
                  }`}
                >
                  <div className="text-sm font-medium text-slate-800 truncate">
                    {j.position || "未命名岗位"}
                  </div>
                  <div className="text-xs text-slate-500 truncate">
                    #{j.id} · {j.company || "-"} · {j.city || "-"} ·{" "}
                    {j.salary_min != null && j.salary_max != null
                      ? `${j.salary_min}-${j.salary_max}K`
                      : "薪资面议"}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* ---- 简历 + 押题数 ---- */}
          <div className="space-y-4">
            <div>
              <label className="label">基础简历（已解析）</label>
              <select
                className="input"
                value={resumeId}
                onChange={(e) =>
                  setResumeId(e.target.value ? Number(e.target.value) : "")
                }
              >
                <option value="">— 选择 —</option>
                {resumes
                  .filter((r) => r.parse_status === "COMPLETED")
                  .map((r) => (
                    <option key={r.id} value={r.id}>
                      #{r.id} {r.original_filename}
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <label className="label">押题数量</label>
              <input
                className="input"
                type="number"
                min={1}
                max={20}
                value={count}
                onChange={(e) => setCount(Number(e.target.value) || 5)}
              />
            </div>
            <button className="btn-primary w-full" onClick={submit} disabled={submitting}>
              {submitting ? "正在生成简历…" : "生成定制简历"}
            </button>
            <p className="text-xs text-slate-500 leading-5">
              流水线：召回评估 → 差距分析 → <b>定制简历</b> → 面试押题。
              当前默认 provider 是 <b>mock</b>，会用<b>本地规则</b>产出（秒级完成）；
              在「模型管理」配置真实 LLM 后自动切换为语义级改写。
            </p>
          </div>
        </div>
      </Card>

      <Card title={`定制化任务 (${list?.total ?? 0})`}>
        {!list && <p className="text-sm text-gray-500">加载中…</p>}
        {list && list.items.length === 0 && (
          <p className="text-sm text-gray-500">还没有任务。</p>
        )}
        {list && list.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="py-2">ID</th>
                  <th>JD / 简历</th>
                  <th>状态</th>
                  <th>Provider</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {list.items.map((c) => (
                  <tr key={c.id} className="border-b last:border-0">
                    <td className="py-2">{c.id}</td>
                    <td>
                      JD #{c.jd_id} · 简历 #{c.base_resume_id}
                    </td>
                    <td>
                      <StatusBadge status={c.status} />
                      {c.error_message && (
                        <span className="ml-2 text-xs text-red-500">
                          {c.error_message.slice(0, 60)}
                        </span>
                      )}
                    </td>
                    <td className="text-gray-500">{c.provider_used ?? "-"}</td>
                    <td className="text-gray-500">
                      {new Date(c.created_at).toLocaleString()}
                    </td>
                    <td className="space-x-2 whitespace-nowrap">
                      <button
                        className="text-brand-600 hover:underline"
                        onClick={() => showDetail(c.id)}
                      >
                        详情
                      </button>
                      {c.status === "COMPLETED" && (
                        <>
                          <button
                            className="text-brand-600 hover:underline font-medium"
                            onClick={() => download(c.id, "resume-pdf")}
                          >
                            简历PDF
                          </button>
                          <button
                            className="text-brand-600 hover:underline"
                            onClick={() => download(c.id, "docx")}
                          >
                            DOCX
                          </button>
                          <button
                            className="text-slate-500 hover:underline"
                            onClick={() => download(c.id, "report")}
                          >
                            分析报告
                          </button>
                        </>
                      )}
                      {c.status === "FAILED" && (
                        <button
                          className="text-blue-500 hover:underline"
                          onClick={() => onRetry(c.id)}
                        >
                          重试
                        </button>
                      )}
                      <button
                        className="text-red-500 hover:underline"
                        onClick={() => onDelete(c.id)}
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-slate-400 mt-2">
              点「简历PDF / DOCX」会下载到浏览器默认下载目录。
              若点击后没反应，请检查浏览器是否拦截了本站下载。
            </p>
          </div>
        )}
      </Card>

      {detail && (
        <CustomizationDetailView
          detail={detail}
          busy={savingSuggestions}
          onApplySuggestions={applySuggestions}
          onDownload={download}
        />
      )}
    </div>
  );
}

/* ---------------- 详情：以「简历」为主，分析为辅 ---------------- */

function CustomizationDetailView({
  detail,
  busy,
  onApplySuggestions,
  onDownload,
}: {
  detail: CustomizationDetail;
  busy: boolean;
  onApplySuggestions: (ids: string[] | null, confirmed: boolean) => void;
  onDownload: (id: number, kind: "resume-pdf" | "docx" | "report") => void;
}) {
  const cr = (detail.customized_resume ?? {}) as Partial<TailoredResume>;
  const content = cr.content;
  const suggestions: TailorSuggestion[] = cr.suggestions ?? [];
  const groups = cr.skill_groups ?? [];
  const notes = cr.tailor_notes ?? [];
  const ranking = cr.ranking ?? [];
  const pending = suggestions.filter((s) => !s.confirmed);

  const modes = [
    (detail.gap_report as Record<string, unknown> | null)?.extract_mode,
    cr.extract_mode,
    (detail.prediction as Record<string, unknown> | null)?.extract_mode,
  ].filter(Boolean) as string[];
  const isHeuristic = modes.includes("heuristic");

  // 旧版「报告格式」记录：没有简历正文
  if (!content) {
    return (
      <Card title={`报告 #${detail.id}`}>
        <div className="rounded-xl border border-amber-200 bg-amber-50 text-amber-800 px-3 py-2 text-xs leading-5 mb-4">
          这条记录是<b>旧版「报告格式」</b>，不含简历正文。
          请点「详情」旁边的路径重新生成：直接删除本条后重新发起一次定制化，即可得到简历形态的产物。
        </div>
        <LegacyReport detail={detail} />
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card title={`简历 #${detail.id} · ${cr.target_position || content.profile.title}`}>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <button
            className="btn-primary text-sm"
            onClick={() => onDownload(detail.id, "resume-pdf")}
          >
            下载简历 PDF
          </button>
          <button
            className="btn-ghost text-sm"
            onClick={() => onDownload(detail.id, "docx")}
          >
            下载 DOCX（可编辑）
          </button>
          <button
            className="text-sm text-slate-500 hover:underline px-2"
            onClick={() => onDownload(detail.id, "report")}
          >
            导出分析报告
          </button>
          {pending.length > 0 && (
            <span className="ml-auto text-xs rounded-full bg-amber-100 text-amber-800 px-3 py-1">
              {pending.length} 项待确认（未确认内容带标记，不会冒充你的经历）
            </span>
          )}
        </div>

        {isHeuristic && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 text-amber-800 px-3 py-2 text-xs leading-5 mb-3">
            当前由<b>本地规则</b>生成（未接入真实 LLM）：经历按岗位相关度重排、
            技能按类别归位，<b>不会新增你简历里没有的事实</b>。
            想要语义级改写，请在「模型管理」配置真实 Provider。
          </div>
        )}

        {/* 简历正文预览：与导出的 PDF / DOCX 内容完全一致 */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 max-h-[560px] overflow-auto">
          <pre className="whitespace-pre-wrap font-sans text-[13px] leading-6 text-slate-800">
            {(detail.resume_text || "").split("\n").map((line, i) => (
              <div
                key={i}
                className={
                  line.includes(UNCONFIRMED_TAG)
                    ? "bg-amber-50 text-amber-900 rounded px-1"
                    : undefined
                }
              >
                {line || " "}
              </div>
            ))}
          </pre>
        </div>
      </Card>

      {groups.length > 0 && (
        <Card title="技能归位（按岗位相关度排序）">
          <div className="space-y-2 text-sm">
            {groups.map((g) => (
              <div key={g.category} className="flex gap-3">
                <div className="w-28 shrink-0 text-gray-500">{g.category}</div>
                <div className="flex flex-wrap gap-1">
                  {g.items.map((s) => (
                    <span key={s} className="badge bg-gray-100 text-gray-700">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card title={`待确认的补足建议 (${suggestions.length})`}>
        {suggestions.length === 0 && (
          <p className="text-sm text-gray-500">
            岗位要求的关键词在简历里都有依据，没有需要补充的内容。
          </p>
        )}
        {suggestions.length > 0 && (
          <>
            <div className="flex items-center gap-2 mb-3">
              <button
                className="btn-ghost text-xs"
                disabled={busy}
                onClick={() => onApplySuggestions(null, true)}
              >
                全部确认
              </button>
              <button
                className="text-xs text-slate-500 hover:underline px-2"
                disabled={busy}
                onClick={() => onApplySuggestions(null, false)}
              >
                全部驳回
              </button>
              <span className="text-xs text-slate-400">
                确认 = 这句表述符合你的真实经历，去掉「未证实」标记；驳回 = 保留建议但不写进简历。
              </span>
            </div>
            <ul className="space-y-3">
              {suggestions.map((s) => (
                <li
                  key={s.id}
                  className={`rounded-xl border px-3 py-2 ${
                    s.confirmed
                      ? "border-emerald-200 bg-emerald-50"
                      : "border-amber-200 bg-amber-50"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="flex-1">
                      <div className="text-xs text-gray-500 mb-1">
                        位置：{s.target_label} · 对应岗位要求：
                        <b className="text-gray-700">{s.skill}</b>
                        {s.priority === "HIGH" && (
                          <span className="ml-2 text-red-600 font-bold">高优先</span>
                        )}
                      </div>
                      <div className="text-sm text-slate-800">{s.text}</div>
                      {s.reason && (
                        <div className="text-xs text-gray-500 mt-1">
                          依据：{s.reason}
                        </div>
                      )}
                    </div>
                    <div className="shrink-0 space-x-2 whitespace-nowrap">
                      {s.confirmed ? (
                        <>
                          <span className="badge bg-emerald-100 text-emerald-700">
                            已确认
                          </span>
                          <button
                            className="text-xs text-slate-500 hover:underline"
                            disabled={busy}
                            onClick={() => onApplySuggestions([s.id], false)}
                          >
                            撤回
                          </button>
                        </>
                      ) : (
                        <>
                          <span className="badge bg-amber-100 text-amber-700">
                            未证实
                          </span>
                          <button
                            className="text-xs text-brand-600 hover:underline font-medium"
                            disabled={busy}
                            onClick={() => onApplySuggestions([s.id], true)}
                          >
                            确认采用
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <details className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
        <summary className="cursor-pointer text-sm font-medium text-slate-700">
          本次定制做了什么（{notes.length} 条调整说明）
        </summary>
        <div className="mt-3 space-y-3 text-sm">
          <ul className="list-disc pl-5 text-gray-700">
            {notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
          {ranking.length > 0 && (
            <div>
              <div className="text-gray-500 text-xs mb-1">经历与岗位相关度</div>
              <div className="space-y-1">
                {ranking.map((r, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="w-12 shrink-0 text-right text-gray-500">
                      {r.score} 分
                    </span>
                    <div className="flex-1 h-2 rounded bg-slate-100 overflow-hidden">
                      <div
                        className="h-full bg-brand-400"
                        style={{ width: `${Math.max(2, r.score)}%` }}
                      />
                    </div>
                    <span className="text-slate-700">{r.title}</span>
                    <span className="text-gray-400">
                      {r.matched_skills.join("、") || "无直接命中"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </details>

      <details className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
        <summary className="cursor-pointer text-sm font-medium text-slate-700">
          分析报告（差距分析 / 面试押题 / 召回指标）
        </summary>
        <div className="mt-3">
          <LegacyReport detail={detail} />
        </div>
      </details>
    </div>
  );
}

/* ---------------- 分析部分（原报告内容） ---------------- */

function LegacyReport({ detail }: { detail: CustomizationDetail }) {
  const gap = (detail.gap_report ?? {}) as Record<string, unknown>;
  const prediction = (detail.prediction ?? {}) as Record<string, unknown>;
  const metrics = (detail.retrieval_metrics ?? {}) as Record<string, unknown>;

  return (
    <div className="space-y-4 text-sm">
      <Section title="差距分析">
        <div className="text-2xl font-bold text-brand-700 mb-2">
          匹配度：{String(gap.match_score ?? 0)} / 100
        </div>
        <div>
          <strong>已匹配技能：</strong>
          <TagList items={toStrArr(gap.matched_skills)} />
        </div>
        <div className="mt-2">
          <strong>缺失技能：</strong>
          {toObjArr(gap.missing_skills).length === 0 ? (
            <span className="text-gray-400">-</span>
          ) : (
            <ul className="list-disc pl-5">
              {toObjArr(gap.missing_skills).map((m, i) => (
                <li key={i}>
                  <span
                    className={
                      m.priority === "HIGH"
                        ? "text-red-600 font-bold"
                        : m.priority === "MEDIUM"
                          ? "text-yellow-600"
                          : "text-blue-500"
                    }
                  >
                    [{String(m.priority)}]
                  </span>{" "}
                  {String(m.skill)}{" "}
                  <span className="text-gray-500">— {String(m.reason)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        {toObjArr(gap.experience_gaps).length > 0 && (
          <div className="mt-2">
            <strong>硬性条件差距：</strong>
            <ul className="list-disc pl-5">
              {toObjArr(gap.experience_gaps).map((g, i) => (
                <li key={i}>
                  {String(g.aspect)}：当前 {String(g.current)} / 要求{" "}
                  {String(g.expected)}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="mt-2">
          <strong>建议重点：</strong>
          <ul className="list-disc pl-5 text-gray-700">
            {toStrArr(gap.recommended_focus).map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      </Section>

      <Section title="面试预测">
        {toObjArr(prediction.questions).length === 0 ? (
          <p className="text-gray-400">-</p>
        ) : (
          <ul className="space-y-3">
            {toObjArr(prediction.questions).map((q, i) => (
              <li
                key={i}
                className="border-l-4 border-brand-500 pl-3 py-1 bg-gray-50"
              >
                <div>
                  <span className="badge bg-brand-100 text-brand-700">
                    {String(q.category)} / {String(q.difficulty)}
                  </span>{" "}
                  <strong>{String(q.question)}</strong>
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  为什么被问到: {String(q.hit_reason)}
                </div>
                <div className="text-xs mt-1 space-y-0.5">
                  {(["situation", "task", "action", "result"] as const).map((k) => (
                    <div key={k}>
                      <strong>{k[0].toUpperCase()}:</strong>{" "}
                      {String(
                        (q.star_answer as Record<string, unknown>)?.[k],
                      )}
                    </div>
                  ))}
                </div>
                <div className="text-xs mt-1 text-gray-600">
                  关键点: {toStrArr(q.key_points).join(" / ")}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="召回评估指标">
        <MetricRow label="混合" data={metrics.hybrid} />
        <MetricRow label="纯向量" data={metrics.vector_only} />
        <MetricRow label="关键词" data={metrics.keyword_only} />
        <p className="text-xs text-slate-400 mt-1">
          注：库里只有 1 份简历时，召回指标恒为 1.0（ground truth 就是它自己），多传几份简历才有区分度。
        </p>
      </Section>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-base font-semibold text-brand-700 border-b pb-1 mb-2">
        {title}
      </h3>
      {children}
    </div>
  );
}

function TagList({ items }: { items: string[] }) {
  if (items.length === 0) return <span className="text-gray-400">-</span>;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {items.map((s, i) => (
        <span key={i} className="badge bg-gray-100 text-gray-700">
          {s}
        </span>
      ))}
    </span>
  );
}

function MetricRow({ label, data }: { label: string; data: unknown }) {
  const d = (data ?? {}) as Record<string, unknown>;
  return (
    <div className="grid grid-cols-4 gap-2 py-1 text-xs">
      <div className="font-medium">{label}</div>
      <div>Recall@K: {Number(d.recall_at_k ?? 0).toFixed(3)}</div>
      <div>Precision@K: {Number(d.precision_at_k ?? 0).toFixed(3)}</div>
      <div>NDCG@K: {Number(d.ndcg_at_k ?? 0).toFixed(3)}</div>
    </div>
  );
}

function toStrArr(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => String(x));
}
function toObjArr(v: unknown): Record<string, unknown>[] {
  if (!Array.isArray(v)) return [];
  return v as Record<string, unknown>[];
}
