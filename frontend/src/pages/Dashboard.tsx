import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { HealthData } from "../types";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUpRight, BriefcaseBusiness, FileText, Server, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";

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
    <div className="space-y-7">
      <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="relative overflow-hidden rounded-3xl bg-slate-900 text-white p-7 sm:p-10">
        <div className="absolute right-[-4rem] top-[-5rem] h-64 w-64 rounded-full border-[35px] border-brand-500/20" />
        <div className="relative max-w-2xl">
          <div className="inline-flex items-center gap-2 text-brand-300 text-sm font-semibold mb-4"><Sparkles size={16} /> LOCAL-FIRST CAREER WORKSPACE</div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-3">把每一次投递，<span className="text-brand-300">变成更好的版本。</span></h1>
          <p className="text-slate-300 leading-7">集中管理简历与职位，快速看到匹配差距，再生成更贴合目标岗位的求职材料。</p>
        </div>
      </motion.section>

      <AnimatePresence>{error && <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="card border-red-200 bg-red-50 text-red-700">后端未连通：{error}。请确认 backend 已起在 :8000。</motion.div>}</AnimatePresence>

      {health && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Stat label="服务状态" value={health.status} ok={health.status === "ok"} />
          <Stat label="数据库" value={health.db ? "已连" : "未连"} ok={health.db} />
          <Stat label="版本" value={health.version} ok />
        </div>
      )}

      <div className="grid lg:grid-cols-[1.4fr_0.9fr] gap-5">
        <section>
          <div className="flex items-end justify-between mb-3"><div><p className="eyebrow">WORKFLOW</p><h2 className="text-xl font-bold">从资料到投递</h2></div><span className="text-xs text-slate-400">4 个核心步骤</span></div>
          <div className="grid sm:grid-cols-2 gap-4">
            <QuickLink to="/resumes" title="简历管理" desc="上传 → 自动拆解 → 在线编辑 → 导出下载" icon={FileText} number="01" />
            <QuickLink to="/jds" title="提交目标职位" desc="粘贴文本或职位 URL" icon={BriefcaseBusiness} number="02" />
            <QuickLink to="/customizations" title="发起定制化" desc="差距分析与面试押题" icon={Sparkles} number="03" />
            <QuickLink to="/settings" title="模型管理" desc="配置默认 LLM Provider" icon={Server} number="04" />
          </div>
        </section>
        <section className="card min-h-56">
          <p className="eyebrow">ACTIVITY</p><h2 className="text-xl font-bold mb-1">工作流概览</h2><p className="text-sm text-slate-500 mb-4">你的求职资料准备节奏</p>
          <ResponsiveContainer width="100%" height={125}><AreaChart data={[{ day: "一", value: 2 }, { day: "二", value: 4 }, { day: "三", value: 3 }, { day: "四", value: 6 }, { day: "五", value: 5 }, { day: "六", value: 8 }, { day: "日", value: 7 }]}><defs><linearGradient id="activity" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#16a085" stopOpacity={0.35} /><stop offset="100%" stopColor="#16a085" stopOpacity={0} /></linearGradient></defs><XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fill: "#94a3b8", fontSize: 11 }} /><Tooltip /><Area type="monotone" dataKey="value" stroke="#16a085" fill="url(#activity)" strokeWidth={3} /></AreaChart></ResponsiveContainer>
        </section>
      </div>

      <section className="border-t pt-6"><p className="eyebrow">GET STARTED</p><h2 className="text-xl font-bold mb-3">推荐使用顺序</h2><ol className="grid md:grid-cols-5 gap-3 text-sm text-slate-600">
        <li>在「模型管理」新增一个 Provider（API Key 必填）并设为默认</li>
        <li>「简历管理」上传一份基础简历 → 自动拆解为可编辑文本 → 需要时直接改并导出</li>
        <li>「JD」粘贴 JD 文本 → 等待结构化完成</li>
        <li>「定制化」选 (JD, 简历) 发起 → 轮询到 COMPLETED</li>
        <li>点详情查看 差距 / 定制 / 押题 / 召回指标，并导出 PDF</li>
      </ol></section>
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

function QuickLink({ to, title, desc, icon: Icon, number }: { to: string; title: string; desc: string; icon: typeof FileText; number: string }) {
  return (
    <Link to={to} className="group card hover:border-brand-500 hover:-translate-y-0.5 transition duration-200">
      <div className="flex items-center justify-between mb-5"><span className="grid place-items-center w-10 h-10 rounded-xl bg-brand-50 text-brand-600"><Icon size={19} /></span><span className="text-xs font-bold text-slate-300">{number}</span></div>
      <div className="flex items-center justify-between"><div><div className="font-semibold text-slate-800">{title}</div><div className="text-xs text-slate-500 mt-1">{desc}</div></div><ArrowUpRight size={17} className="text-slate-300 group-hover:text-brand-600 transition" /></div>
    </Link>
  );
}
