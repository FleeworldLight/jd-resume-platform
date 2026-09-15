import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { PageResp, Resume, ResumeDetail, ResumeStatus } from "../types";
import { Card, ErrorBanner, PageHero, StatusBadge } from "../components";
import ResumeEditor from "../components/ResumeEditor";
import {
  CheckCircle2,
  Download,
  FileDown,
  FileText,
  Info,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from "lucide-react";

/** 导出按钮支持的格式 */
const EXPORT_FORMATS = ["pdf", "docx", "txt"] as const;

/** 去掉文件扩展名，用于导出时的文件名 */
function stemOf(filename: string): string {
  return filename.replace(/\.[^.]+$/, "") || "resume";
}

export default function Resumes() {
  const [list, setList] = useState<PageResp<Resume> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string>("");

  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // ---- 在线编辑状态 ----
  // 编辑器的脏值/保存状态由 <ResumeEditor> 自己维护（它需要结构化内容来判断）
  const [editing, setEditing] = useState<ResumeDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  // 改变它可强制编辑器重挂载（重新解析后需要重新拉取内容）
  const [editorKey, setEditorKey] = useState(0);

  const reload = async () => {
    try {
      setList(await api.get<PageResp<Resume>>("/api/resumes?page_size=50"));
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    reload();
  }, []);

  // 轮询未完成项
  useEffect(() => {
    if (!list) return;
    const pending = list.items.filter(
      (r) => r.parse_status === "PENDING" || r.parse_status === "PROCESSING",
    );
    if (pending.length === 0) return;
    const timer = setInterval(async () => {
      let changed = false;
      for (const r of pending) {
        try {
          const s = await api.get<ResumeStatus>(`/api/resumes/${r.id}/status`);
          if (s.parse_status === "COMPLETED" || s.parse_status === "FAILED") {
            changed = true;
          }
        } catch {
          /* 忽略单次失败 */
        }
      }
      if (changed) reload();
    }, 2000);
    return () => clearInterval(timer);
  }, [list]);

  // ---- 上传 ----
  const doUpload = async (f: File) => {
    setError(null);
    setNotice("");
    setUploading(true);
    try {
      const created = await api.upload<Resume>("/api/resumes", f);
      setNotice(`《${created.original_filename}》上传成功，已自动拆解，可直接点「查看 / 编辑」修改。`);
      await reload();
    } catch (e) {
      setError(e);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  // ---- 打开编辑器 ----
  const openEditor = async (id: number) => {
    setError(null);
    setNotice("");
    setLoadingDetail(true);
    try {
      const detail = await api.get<ResumeDetail>(`/api/resumes/${id}`);
      setEditing(detail);
      window.setTimeout(() => {
        document.getElementById("resume-editor")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 50);
    } catch (e) {
      setError(e);
    } finally {
      setLoadingDetail(false);
    }
  };

  const closeEditor = () => {
    setEditing(null);
  };

  // ---- 重新解析 ----
  const reparse = async (id: number) => {
    if (!confirm("重新解析会用在库里的「编辑内容」吗？\n\n不会。重新解析是从上传的原文件重新提取文本，会覆盖当前编辑内容。确定继续？")) return;
    setError(null);
    setBusyId(id);
    try {
      await api.post(`/api/resumes/${id}/reparse`);
      await reload();
      if (editing?.id === id) {
        const detail = await api.get<ResumeDetail>(`/api/resumes/${id}`);
        setEditing(detail);
        // 重新解析后要强制编辑器重新拉取结构化内容（用 key 触发重挂载）
        setEditorKey((k) => k + 1);
      }
      setNotice("已重新解析。");
    } catch (e) {
      setError(e);
    } finally {
      setBusyId(null);
    }
  };

  // ---- 导出编辑后的版本 ----
  const exportAs = async (id: number, filename: string, fmt: string) => {
    setError(null);
    setBusyId(id);
    try {
      await api.download(`/api/resumes/${id}/export?fmt=${fmt}`, `${stemOf(filename)}.${fmt}`);
      setNotice(`已导出 ${fmt.toUpperCase()}。`);
    } catch (e) {
      setError(e);
    } finally {
      setBusyId(null);
    }
  };

  // ---- 下载原文件 ----
  const downloadOriginal = async (id: number, filename: string) => {
    setError(null);
    try {
      await api.download(`/api/resumes/${id}/file`, filename);
    } catch (e) {
      setError(e);
    }
  };

  const remove = async (id: number) => {
    if (!confirm(`确定删除简历 #${id}？该操作不可恢复。`)) return;
    setError(null);
    try {
      await api.del(`/api/resumes/${id}`);
      if (editing?.id === id) closeEditor();
      await reload();
    } catch (e) {
      setError(e);
    }
  };

  return (
    <div className="space-y-4">
      <PageHero
        eyebrow="RESUME STUDIO"
        title="简历管理"
        desc="上传 → 自动拆解为可编辑文本 → 在线编辑 → 导出 PDF / DOCX / TXT。支持点击选择或直接把文件拖进上传框。"
      />
      {/* ---------- 流程引导 ---------- */}
      <div className="rounded-2xl border border-slate-200 bg-slate-50/70 px-4 py-3">
        <div className="flex items-start gap-2 text-sm text-slate-600">
          <Info size={16} className="mt-0.5 shrink-0 text-brand-600" />
          <div>
            <span className="font-medium text-slate-700">简历管理怎么用：</span>
            上传 → 自动拆解为可编辑文本 → 点「查看 / 编辑」直接改 → 「保存」→ 导出 PDF / DOCX / TXT。
            <span className="block text-xs text-slate-500 mt-1">
              上传的原文件不会被改动，随时可以「下载原件」；导出的是你编辑后的版本。
            </span>
          </div>
        </div>
      </div>

      {/* ---------- 上传区 ---------- */}
      <Card title="上传简历" action={<span className="text-xs text-slate-400">支持 PDF / DOCX / TXT，单个 ≤ 10MB</span>}>
        <ErrorBanner error={error} />
        {notice && (
          <div className="mb-4 flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
            <span>{notice}</span>
          </div>
        )}

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files?.[0];
            if (f) doUpload(f);
          }}
        >
          {/* 用 label + htmlFor 触发系统文件选择框，比 onClick 更稳 */}
          <label
            htmlFor="resume-file-input"
            className={`flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-9 text-center transition cursor-pointer ${
              dragging
                ? "border-brand-500 bg-brand-50"
                : "border-slate-300 bg-white hover:border-brand-400 hover:bg-slate-50"
            } ${uploading ? "pointer-events-none opacity-60" : ""}`}
          >
            <span className="grid place-items-center w-11 h-11 rounded-xl bg-brand-50 text-brand-600">
              {uploading ? <Loader2 size={20} className="animate-spin" /> : <Upload size={20} />}
            </span>
            <span className="font-medium text-slate-800">
              {uploading ? "正在上传并解析…" : "点击这里选择简历文件"}
            </span>
            <span className="text-xs text-slate-500">也可以把文件直接拖进这个方框</span>
            <span className="mt-1 inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3.5 py-1.5 text-sm font-medium text-white shadow-sm">
              <FileText size={15} /> 选择文件
            </span>
          </label>
          <input
            id="resume-file-input"
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) doUpload(f);
            }}
          />
        </div>
      </Card>

      {/* ---------- 在线编辑器 ---------- */}
      {editing && (
        <div id="resume-editor">
          <Card
            title={`编辑简历 · ${editing.original_filename}`}
            action={
              <button
                onClick={closeEditor}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
              >
                <X size={15} /> 关闭
              </button>
            }
          >
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <StatusBadge status={editing.parse_status} />
              <span className="text-xs text-slate-500">
                结构化编辑：左侧改字段，右侧实时预览
              </span>
              <span className="ml-auto flex flex-wrap items-center gap-2">
                <button
                  onClick={() => reparse(editing.id)}
                  disabled={busyId === editing.id}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  <RefreshCw size={15} /> 重新解析
                </button>
                <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700">
                  <FileDown size={15} /> 导出
                  {EXPORT_FORMATS.map((f) => (
                    <button
                      key={f}
                      onClick={() => exportAs(editing.id, editing.original_filename, f)}
                      className="rounded px-1.5 py-0.5 text-xs font-medium uppercase text-brand-700 hover:bg-brand-50"
                    >
                      {f}
                    </button>
                  ))}
                </span>
                <button
                  onClick={() => downloadOriginal(editing.id, editing.original_filename)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
                >
                  <Download size={15} /> 下载原件
                </button>
              </span>
            </div>

            <ResumeEditor key={editorKey} resume={editing} onSaved={reload} />
          </Card>
        </div>
      )}

      {/* ---------- 简历列表 ---------- */}
      <Card title={`简历列表 (${list?.total ?? 0})`}>
        {!list && (
          <p className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 size={15} className="animate-spin" /> 加载中…
          </p>
        )}
        {list && list.items.length === 0 && (
          <p className="text-sm text-slate-500">还没有简历，点上面的方框上传第一份吧。</p>
        )}
        {list && list.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b">
                  <th className="py-2 pr-3">ID</th>
                  <th className="pr-3">文件名</th>
                  <th className="pr-3">状态</th>
                  <th className="pr-3">上传时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {list.items.map((r) => (
                  <tr key={r.id} className="border-b last:border-0 align-top">
                    <td className="py-2.5 pr-3 text-slate-500">{r.id}</td>
                    <td className="pr-3 max-w-[220px]">
                      <div className="truncate font-medium text-slate-800" title={r.original_filename}>
                        {r.original_filename}
                      </div>
                    </td>
                    <td className="pr-3">
                      <StatusBadge status={r.parse_status} />
                      {r.parse_error && (
                        <div className="mt-1 text-xs text-red-500">{r.parse_error.slice(0, 80)}</div>
                      )}
                    </td>
                    <td className="pr-3 whitespace-nowrap text-slate-500">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        <button
                          onClick={() => openEditor(r.id)}
                          className="inline-flex items-center gap-1 font-medium text-brand-700 hover:underline"
                        >
                          <Pencil size={14} /> 查看 / 编辑
                        </button>
                        <button
                          onClick={() => exportAs(r.id, r.original_filename, "pdf")}
                          className="inline-flex items-center gap-1 text-slate-600 hover:underline"
                        >
                          <FileDown size={14} /> 导出
                        </button>
                        <button
                          onClick={() => downloadOriginal(r.id, r.original_filename)}
                          className="inline-flex items-center gap-1 text-slate-600 hover:underline"
                        >
                          <Download size={14} /> 原件
                        </button>
                        <button
                          onClick={() => reparse(r.id)}
                          disabled={busyId === r.id}
                          className="inline-flex items-center gap-1 text-slate-600 hover:underline disabled:opacity-40"
                        >
                          <RefreshCw size={14} /> 重解析
                        </button>
                        <button
                          onClick={() => remove(r.id)}
                          className="inline-flex items-center gap-1 text-red-500 hover:underline"
                        >
                          <Trash2 size={14} /> 删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {loadingDetail && (
          <p className="mt-3 flex items-center gap-2 text-sm text-slate-500">
            <Loader2 size={15} className="animate-spin" /> 正在读取解析结果…
          </p>
        )}
      </Card>
    </div>
  );
}
