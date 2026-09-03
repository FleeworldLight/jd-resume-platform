import { useEffect, useState } from "react";
import { api } from "../api";
import type { LlmProvider } from "../types";
import { Card, ErrorBanner } from "../components";

const PROVIDER_TYPES = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "mock", label: "Mock（测试用）" },
];

export default function Settings() {
  const [list, setList] = useState<LlmProvider[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [info, setInfo] = useState<string>("");

  const [name, setName] = useState("");
  const [ptype, setPtype] = useState("openai");
  const [baseUrl, setBaseUrl] = useState("");
  const [chatModel, setChatModel] = useState("");
  const [embedModel, setEmbedModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [isDefault, setIsDefault] = useState(false);

  const reload = async () => {
    try {
      setList(await api.get<LlmProvider[]>("/api/llm-providers"));
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    reload();
  }, []);

  const create = async () => {
    setError(null);
    setInfo("");
    try {
      await api.post<LlmProvider>("/api/llm-providers", {
        name,
        provider_type: ptype,
        base_url: baseUrl || null,
        chat_model: chatModel || null,
        embedding_model: embedModel || null,
        api_key: apiKey || null,
        is_default: isDefault,
        enabled: true,
      });
      setName("");
      setApiKey("");
      setBaseUrl("");
      setChatModel("");
      setEmbedModel("");
      setIsDefault(false);
      setInfo("已创建");
      reload();
    } catch (e) {
      setError(e);
    }
  };

  const setDefault = async (id: number) => {
    try {
      await api.post(`/api/llm-providers/${id}/set-default`);
      reload();
    } catch (e) {
      setError(e);
    }
  };

  const test = async (id: number) => {
    setError(null);
    setInfo("");
    try {
      const r = await api.post<{ ok: boolean; message?: string; error?: string }>(
        `/api/llm-providers/${id}/test`,
      );
      if (r.ok) setInfo(`✅ ${r.message ?? "ok"}`);
      else setInfo(`❌ ${r.error ?? "failed"}`);
    } catch (e) {
      setError(e);
    }
  };

  const del = async (id: number) => {
    if (!confirm(`删除 Provider ${id}?`)) return;
    try {
      await api.del(`/api/llm-providers/${id}`);
      reload();
    } catch (e) {
      setError(e);
    }
  };

  return (
    <div className="space-y-4">
      <ErrorBanner error={error} />
      {info && (
        <div className="card border-blue-200 bg-blue-50 text-blue-700 text-sm">
          {info}
        </div>
      )}

      <Card title="新增 LLM Provider">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="label">名称</label>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my-openai"
            />
          </div>
          <div>
            <label className="label">类型</label>
            <select
              className="input"
              value={ptype}
              onChange={(e) => setPtype(e.target.value)}
            >
              {PROVIDER_TYPES.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Base URL（可选）</label>
            <input
              className="input"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
            />
          </div>
          <div>
            <label className="label">Chat 模型</label>
            <input
              className="input"
              value={chatModel}
              onChange={(e) => setChatModel(e.target.value)}
              placeholder="gpt-4o-mini"
            />
          </div>
          <div>
            <label className="label">Embedding 模型</label>
            <input
              className="input"
              value={embedModel}
              onChange={(e) => setEmbedModel(e.target.value)}
              placeholder="text-embedding-3-small"
            />
          </div>
          <div>
            <label className="label">API Key</label>
            <input
              type="password"
              className="input"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
            />
          </div>
        </div>
        <label className="inline-flex items-center gap-2 mt-3 text-sm">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
          />
          设为默认
        </label>
        <div className="mt-3">
          <button
            className="btn-primary"
            onClick={create}
            disabled={!name || !ptype}
          >
            创建
          </button>
        </div>
      </Card>

      <Card title={`Provider 列表 (${list?.length ?? 0})`}>
        {!list && <p className="text-sm text-gray-500">加载中…</p>}
        {list && list.length === 0 && (
          <p className="text-sm text-gray-500">还没有 Provider。先创建一个。</p>
        )}
        {list && list.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="py-2">ID</th>
                <th>名称</th>
                <th>类型</th>
                <th>Chat</th>
                <th>Embedding</th>
                <th>API Key</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {list.map((p) => (
                <tr key={p.id} className="border-b last:border-0">
                  <td className="py-2">{p.id}</td>
                  <td>
                    {p.name}
                    {p.is_default && (
                      <span className="ml-2 badge bg-brand-100 text-brand-700">
                        DEFAULT
                      </span>
                    )}
                  </td>
                  <td>{p.provider_type}</td>
                  <td className="text-xs">{p.chat_model ?? "-"}</td>
                  <td className="text-xs">{p.embedding_model ?? "-"}</td>
                  <td className="text-xs">
                    {p.has_api_key ? p.api_key_masked : (
                      <span className="text-red-500">未配置</span>
                    )}
                  </td>
                  <td>{p.enabled ? "启用" : "禁用"}</td>
                  <td className="space-x-2">
                    {!p.is_default && (
                      <button
                        className="text-brand-600 hover:underline"
                        onClick={() => setDefault(p.id)}
                      >
                        设为默认
                      </button>
                    )}
                    <button
                      className="text-blue-500 hover:underline"
                      onClick={() => test(p.id)}
                    >
                      测试
                    </button>
                    <button
                      className="text-red-500 hover:underline"
                      onClick={() => del(p.id)}
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
