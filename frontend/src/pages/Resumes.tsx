import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import type { PageResp, Resume, ResumeStatus } from "../types";
import { Card, ErrorBanner, StatusBadge } from "../components";

export default function Resumes() {
  const [list, setList] = useState<PageResp<Resume> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const pollingIds = useRef<Set<number>>(new Set());

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
      for (const r of pending) {
        if (pollingIds.current.has(r.id)) continue;
        pollingIds.current.add(r.id);
        try {
          const s = await api.get<ResumeStatus>(`/api/resumes/${r.id}/status`);
          if (s.parse_status === "COMPLETED" || s.parse_status === "FAILED") {
            reload();
            pollingIds.current.delete(r.id);
          }
        } catch (e) {
          pollingIds.current.delete(r.id);
        }
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [list]);

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setError(null);
    setUploading(true);
    try {
      await api.upload<Resume>("/api/resumes", f);
      await reload();
    } catch (e) {
      setError(e);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onDelete = async (id: number) => {
    if (!confirm(`删除简历 ${id}?`)) return;
    try {
      await api.del(`/api/resumes/${id}`);
      reload();
    } catch (e) {
      setError(e);
    }
  };

  const onDownload = (id: number, filename: string) => {
    api.download(`/api/resumes/${id}/file`, filename).catch((e) => setError(e));
  };

  return (
    <div className="space-y-4">
      <Card
        title="上传简历"
        action={
          <span className="text-xs text-gray-400">
            支持 PDF / DOCX / TXT，≤ 10MB
          </span>
        }
      >
        <ErrorBanner error={error} />
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,.txt"
          onChange={onUpload}
          disabled={uploading}
          className="block"
        />
        {uploading && <p className="text-sm text-gray-500 mt-2">上传中…</p>}
      </Card>

      <Card title={`简历列表 (${list?.total ?? 0})`}>
        {!list && <p className="text-sm text-gray-500">加载中…</p>}
        {list && list.items.length === 0 && (
          <p className="text-sm text-gray-500">还没有简历，先上传一份。</p>
        )}
        {list && list.items.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="py-2">ID</th>
                <th>文件名</th>
                <th>状态</th>
                <th>上传时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {list.items.map((r) => (
                <tr key={r.id} className="border-b last:border-0">
                  <td className="py-2">{r.id}</td>
                  <td className="truncate max-w-xs">{r.original_filename}</td>
                  <td>
                    <StatusBadge status={r.parse_status} />
                    {r.parse_error && (
                      <span className="ml-2 text-xs text-red-500">
                        {r.parse_error.slice(0, 60)}
                      </span>
                    )}
                  </td>
                  <td className="text-gray-500">
                    {new Date(r.created_at).toLocaleString()}
                  </td>
                  <td className="space-x-2">
                    <button
                      className="text-brand-600 hover:underline"
                      onClick={() => onDownload(r.id, r.original_filename)}
                    >
                      下载
                    </button>
                    <button
                      className="text-red-500 hover:underline"
                      onClick={() => onDelete(r.id)}
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
    </div>
  );
}
