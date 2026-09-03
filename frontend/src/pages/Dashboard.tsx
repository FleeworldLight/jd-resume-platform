import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { HealthData } from "../types";

export default function Dashboard() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    api
      .get<HealthData>("/health")
      .then(setHealth)
      .catch((e: ApiError) => setError(e.message));
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">欢迎使用</h1>
      <p className="text-gray-600 mb-6">
        基于 pgvector + 全文检索的混合召回 + LLM 定制化求职平台。
      </p>

      {error && (
        <div className="card border-red-200 bg-red-50 text-red-700 mb-4">
          后端未连通：{error}。请确认 backend 已起在 :8000。
        </div>
      )}

      {health && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <Stat label="服务状态" value={health.status} ok={health.status === "ok"} />
          <Stat label="数据库" value={health.db ? "已连" : "未连"} ok={health.db} />
          <Stat label="版本" value={health.version} ok />
        </div>
      )}

      <h2 className="text-lg font-semibold mb-3">快速入口</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <QuickLink to="/resumes" title="上传简历" desc="PDF / DOCX / TXT" />
        <QuickLink to="/jds" title="提交 JD" desc="粘贴文本 或 牛客/Boss URL" />
        <QuickLink to="/customizations" title="发起定制化" desc="差距分析 + 定制简历 + 押题" />
        <QuickLink to="/settings" title="模型管理" desc="配置 LLM Provider" />
      </div>

      <h2 className="text-lg font-semibold mt-8 mb-3">演示路径</h2>
      <ol className="list-decimal pl-5 space-y-1 text-sm text-gray-700">
        <li>在「模型管理」新增一个 Provider（API Key 必填）并设为默认</li>
        <li>「简历」上传一份基础简历 → 等待解析完成</li>
        <li>「JD」粘贴 JD 文本 → 等待结构化完成</li>
        <li>「定制化」选 (JD, 简历) 发起 → 轮询到 COMPLETED</li>
        <li>点详情查看 差距 / 定制 / 押题 / 召回指标，并导出 PDF</li>
      </ol>
    </div>
  );
}

function Stat({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="card">
      <div className="text-sm text-gray-500">{label}</div>
      <div className={`text-xl font-bold ${ok ? "text-brand-700" : "text-red-500"}`}>
        {value}
      </div>
    </div>
  );
}

function QuickLink({ to, title, desc }: { to: string; title: string; desc: string }) {
  return (
    <a
      href={to}
      className="card hover:border-brand-500 hover:shadow transition cursor-pointer"
    >
      <div className="font-semibold text-brand-700">{title}</div>
      <div className="text-xs text-gray-500 mt-1">{desc}</div>
    </a>
  );
}
