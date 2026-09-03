import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type {
  Customization,
  CustomizationDetail,
  CustomizationStatus,
  Jd,
  PageResp,
  Resume,
} from "../types";
import { Card, ErrorBanner, StatusBadge } from "../components";

export default function Customizations() {
  const [list, setList] = useState<PageResp<Customization> | null>(null);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [jds, setJds] = useState<Jd[]>([]);
  const [error, setError] = useState<unknown>(null);

  const [jdId, setJdId] = useState<number | "">("");
  const [resumeId, setResumeId] = useState<number | "">("");
  const [count, setCount] = useState(5);

  const [detail, setDetail] = useState<CustomizationDetail | null>(null);

  const pollingIds = useRef<Set<number>>(new Set());

  const reload = async () => {
    try {
      const [cs, r, j] = await Promise.all([
        api.get<PageResp<Customization>>("/api/customizations?page_size=50"),
        api.get<PageResp<Resume>>("/api/resumes?page_size=50"),
        api.get<PageResp<Jd>>("/api/jds?page_size=50"),
      ]);
      setList(cs);
      setResumes(r.items);
      setJds(j.items);
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
      (c) => c.status === "PENDING" || c.status === "PROCESSING",
    );
    if (pending.length === 0) return;
    const timer = setInterval(async () => {
      for (const c of pending) {
        if (pollingIds.current.has(c.id)) continue;
        pollingIds.current.add(c.id);
        try {
          const s = await api.get<CustomizationStatus>(
            `/api/customizations/${c.id}/status`,
          );
          if (s.status === "COMPLETED" || s.status === "FAILED") {
            reload();
            pollingIds.current.delete(c.id);
            if (detail && detail.id === c.id) {
              const full = await api.get<CustomizationDetail>(
                `/api/customizations/${c.id}`,
              );
              setDetail(full);
            }
          }
        } catch {
          pollingIds.current.delete(c.id);
        }
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [list, detail]);

  const submit = async () => {
    if (!jdId || !resumeId) {
      setError(new Error("请选择 JD 和简历"));
      return;
    }
    setError(null);
    try {
      await api.post<Customization>("/api/customizations", {
        jd_id: jdId,
        base_resume_id: resumeId,
        question_count: count,
      });
      reload();
    } catch (e) {
      setError(e);
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
      reload();
    } catch (e) {
      setError(e);
    }
  };

  const onRetry = async (id: number) => {
    try {
      await api.post(`/api/customizations/${id}/retry`);
      reload();
    } catch (e) {
      setError(e);
    }
  };

  return (
    <div className="space-y-4">
      <ErrorBanner error={error} />

      <Card title="发起定制化">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="label">JD（已完成结构化）</label>
            <select
              className="input"
              value={jdId}
              onChange={(e) =>
                setJdId(e.target.value ? Number(e.target.value) : "")
              }
            >
              <option value="">— 选择 —</option>
              {jds
                .filter((j) => j.crawl_status === "COMPLETED")
                .map((j) => (
                  <option key={j.id} value={j.id}>
                    #{j.id} {j.company} · {j.position}
                  </option>
                ))}
            </select>
          </div>
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
        </div>
        <button className="btn-primary mt-3" onClick={submit}>
          发起定制化任务
        </button>
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
                  <td className="space-x-2">
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

  return (
    <Card title={`报告 #${detail.id}`}>
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
                  {String(m.skill)} <span className="text-gray-500">— {String(m.reason)}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="mt-2">
            <strong>建议重点：</strong>
            <TagList items={toStrArr(gap.recommended_focus)} />
          </div>
        </Section>

        <Section title="定制版简历">
          <p className="text-gray-700">{String(customized.summary ?? "")}</p>
          <div className="mt-2">
            <strong>技能：</strong>
            <TagList items={toStrArr(customized.skills)} />
          </div>
          <div className="mt-2">
            <strong>经历：</strong>
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
                </li>
              ))}
            </ul>
          </div>
        </Section>

        <Section title="面试预测">
          <ul className="space-y-3">
            {toObjArr(prediction.questions).map((q, i) => (
              <li key={i} className="border-l-4 border-brand-500 pl-3 py-1 bg-gray-50">
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
                    <strong>S:</strong> {String((q.star_answer as Record<string, unknown>)?.situation)}
                  </div>
                  <div>
                    <strong>T:</strong> {String((q.star_answer as Record<string, unknown>)?.task)}
                  </div>
                  <div>
                    <strong>A:</strong> {String((q.star_answer as Record<string, unknown>)?.action)}
                  </div>
                  <div>
                    <strong>R:</strong> {String((q.star_answer as Record<string, unknown>)?.result)}
                  </div>
                </div>
                <div className="text-xs mt-1 text-gray-600">
                  关键点: {toStrArr(q.key_points).join(" / ")}
                </div>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="召回评估指标">
          <MetricRow label="混合" data={metrics.hybrid} />
          <MetricRow label="纯向量" data={metrics.vector_only} />
          <MetricRow label="关键词" data={metrics.keyword_only} />
        </Section>
      </div>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
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
