import { useEffect, useState } from "react";
import { api } from "../api";
import type {
  Customization,
  CustomizationDetail,
  Jd,
  PageResp,
  Resume,
} from "../types";
import { Card, ErrorBanner, StatusBadge } from "../components";

/** 可用于定制化的 JD 状态：PARSED 已抽好字段，COMPLETED 还多跑了一遍结构化 */
const USABLE_JD_STATUS = ["COMPLETED", "PARSED"];

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

  const onDownload = (id: number) => {
    api.downloadPdf(id).catch((e) => setError(e));
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
              {submitting ? "正在跑流水线…" : "发起定制化任务"}
            </button>
            <p className="text-xs text-slate-500 leading-5">
              流水线：召回评估 → 差距分析 → 定制简历 → 面试押题。
              当前默认 provider 是 <b>mock</b>，会用<b>本地规则</b>产出结果（秒级完成）；
              在「模型管理」配置真实 LLM 后自动切换为语义级分析。
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
                      <button
                        className="text-brand-600 hover:underline"
                        onClick={() => onDownload(c.id)}
                      >
                        导出 PDF
                      </button>
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
        )}
      </Card>

      {detail && <CustomizationDetailView detail={detail} />}
    </div>
  );
}

function CustomizationDetailView({ detail }: { detail: CustomizationDetail }) {
  const gap = (detail.gap_report ?? {}) as Record<string, unknown>;
  const customized = (detail.customized_resume ?? {}) as Record<string, unknown>;
  const prediction = (detail.prediction ?? {}) as Record<string, unknown>;
  const metrics = (detail.retrieval_metrics ?? {}) as Record<string, unknown>;

  const modes = [
    gap.extract_mode,
    customized.extract_mode,
    prediction.extract_mode,
  ].filter(Boolean) as string[];
  const isHeuristic = modes.includes("heuristic");

  return (
    <Card title={`报告 #${detail.id}`}>
      <div className="space-y-4 text-sm">
        {isHeuristic && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 text-amber-800 px-3 py-2 text-xs leading-5">
            <b>当前结果是「本地规则」生成的</b>（未接入真实 LLM）。
            匹配度按「JD 技能要求 ∩ 简历技能」计算；定制简历只重排你简历里已有的信息，
            不会编造经历；押题的 STAR 是让你自己填的空骨架。
            想要语义级分析，请在「模型管理」配置一个真实 Provider。
          </div>
        )}

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

        <Section title="定制版简历">
          <p className="text-gray-700">{String(customized.summary ?? "")}</p>
          <div className="mt-2">
            <strong>技能（按岗位相关度排序）：</strong>
            <TagList items={toStrArr(customized.skills)} />
          </div>
          <div className="mt-2">
            <strong>经历：</strong>
            {toObjArr(customized.experiences).length === 0 ? (
              <span className="text-gray-400">
                -（未从简历文本里识别出带时间段的经历块）
              </span>
            ) : (
              <ul className="list-disc pl-5">
                {toObjArr(customized.experiences).map((e, i) => (
                  <li key={i}>
                    <div>
                      {String(e.title)} @ {String(e.company)}{" "}
                      <span className="text-gray-500">({String(e.duration)})</span>
                    </div>
                    <div className="text-gray-700">{String(e.description)}</div>
                    <ul className="list-circle pl-5 text-gray-600">
                      {toStrArr(e.achievements).map((a, j) => (
                        <li key={j}>{a}</li>
                      ))}
                    </ul>
                    {toStrArr(e.tech_stack).length > 0 && (
                      <div className="text-xs text-gray-500 mt-1">
                        技术栈：{toStrArr(e.tech_stack).join("、")}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {toObjArr(customized.education).length > 0 && (
            <div className="mt-2">
              <strong>教育：</strong>
              <ul className="list-disc pl-5">
                {toObjArr(customized.education).map((e, i) => (
                  <li key={i}>
                    {String(e.duration)} {String(e.school)} {String(e.major)}{" "}
                    {String(e.degree)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {toStrArr(customized.highlights).length > 0 && (
            <div className="mt-2">
              <strong>匹配要点：</strong>
              <ul className="list-disc pl-5 text-gray-700">
                {toStrArr(customized.highlights).map((h, i) => (
                  <li key={i}>{h}</li>
                ))}
              </ul>
            </div>
          )}
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
                    <div>
                      <strong>S:</strong>{" "}
                      {String(
                        (q.star_answer as Record<string, unknown>)?.situation,
                      )}
                    </div>
                    <div>
                      <strong>T:</strong>{" "}
                      {String((q.star_answer as Record<string, unknown>)?.task)}
                    </div>
                    <div>
                      <strong>A:</strong>{" "}
                      {String((q.star_answer as Record<string, unknown>)?.action)}
                    </div>
                    <div>
                      <strong>R:</strong>{" "}
                      {String((q.star_answer as Record<string, unknown>)?.result)}
                    </div>
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
    </Card>
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
