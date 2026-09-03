import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import type { Jd, JdStatus, PageResp } from "../types";
import { Card, ErrorBanner, StatusBadge } from "../components";

export default function Jds() {
  const [list, setList] = useState<PageResp<Jd> | null>(null);
  const [error, setError] = useState<unknown>(null);

  const [text, setText] = useState("");
  const [url, setUrl] = useState("");

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
    <div className="space-y-4">
      <ErrorBanner error={error} />

      <Card title="提交 JD">
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
              结构化抽取
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
              异步抓取
            </button>
          </div>
        </div>
      </Card>

      <Card title={`JD 列表 (${list?.total ?? 0})`}>
        {!list && <p className="text-sm text-gray-500">加载中…</p>}
        {list && list.items.length === 0 && (
          <p className="text-sm text-gray-500">还没有 JD。</p>
        )}
        {list && list.items.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="py-2">ID</th>
                <th>来源</th>
                <th>公司 · 岗位</th>
                <th>状态</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {list.items.map((j) => (
                <tr key={j.id} className="border-b last:border-0">
                  <td className="py-2">{j.id}</td>
                  <td>{j.source}</td>
                  <td>
                    {j.company ?? "-"} · {j.position ?? "-"}
                    {j.salary_min && j.salary_max && (
                      <span className="ml-2 text-xs text-gray-400">
                        {j.salary_min}-{j.salary_max}K
                      </span>
                    )}
                  </td>
                  <td>
                    <StatusBadge status={j.crawl_status} />
                    {j.crawl_error && (
                      <span className="ml-2 text-xs text-red-500">
                        {j.crawl_error.slice(0, 60)}
                      </span>
                    )}
                  </td>
                  <td className="text-gray-500">
                    {new Date(j.created_at).toLocaleString()}
                  </td>
                  <td>
                    <button
                      className="text-red-500 hover:underline"
                      onClick={() => onDelete(j.id)}
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
