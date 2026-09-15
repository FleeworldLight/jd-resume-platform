import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type {
  Customization,
  HealthData,
  JdFacets,
  LlmProvider,
  PageResp,
  Resume,
} from "../types";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUpRight, BriefcaseBusiness, FileText, RefreshCw, Server, Sparkles,
} from "lucide-react";
import { Link } from "react-router-dom";

interface LibraryStats {
  resumes: number;
  jobs: number;
  jobsWithSalary: number;
  companies: number;
  customizations: number;
  customizationsDone: number;
  providers: number;
}

export default function Dashboard() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [error, setError] = useState<string>("");
  const [retry, setRetry] = useState(0);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    setRetrying(true);
    setError("");

    api
      .get<HealthData>("/health")
      .then((h) => {
        setHealth(h);
        return Promise.all([
          api.get<PageResp<Resume>>("/api/resumes?page_size=1"),
          api.get<JdFacets>("/api/jds/facets"),
          api.get<PageResp<Customization>>("/api/customizations?page_size=1"),
          api.get<PageResp<Customization>>(
            "/api/customizations?status=COMPLETED&page_size=1",
          ),
          api.get<LlmProvider[]>("/api/llm-providers"),
        ]);
      })
      .then(([resumes, facets, customs, customsDone, providers]) => {
        setStats({
          resumes: resumes.total,
          jobs: facets.total,
          jobsWithSalary: facets.with_salary,
          companies: facets.companies,
          customizations: customs.total,
          customizationsDone: customsDone.total,
          providers: providers.length,
        });
      })
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setRetrying(false));
  }, [retry]);

  return (
    <div className="space-y-7">
      <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="relative overflow-hidden rounded-3xl bg-slate-900 text-white p-7 sm:p-10">
        <div className="absolute right-[-4rem] top-[-5rem] h-64 w-64 rounded-full border-[35px] border-brand-500/20" />
        <div className="relative max-w-2xl">
          <div className="inline-flex items-center gap-2 text-brand-300 text-sm font-semibold mb-4"><Sparkles size={16} /> LOCAL-FIRST CAREER WORKSPACE</div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-3">把每一次投递，<span className="text-brand-300">变成更好的版本。</span></h1>
          <p className="text-slate-300 leading-7">集中管理简历与岗位，先看清匹配差距，再生成更贴合目标岗位的求职材料。数据全部存在本地 SQLite。</p>
        </div>
      </motion.section>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="card border-amber-200 bg-amber-50 text-amber-900"
          >
            <div className="font-semibold mb-1">后端暂时连不上（{error}）</div>
            <p className="text-sm leading-6">
              如果这是线上演示站：免费实例闲置后会休眠，
              <b>首次请求需要 30~60 秒唤醒</b>，点下面的按钮多试几次即可。
            </p>
            <p className="text-sm leading-6">
              如果这是本地运行：请确认后端已启动（双击项目根目录的 <code>start.bat</code>，
              或 <code>uvicorn app.main:app --port 8000</code>）。
            </p>
            <button
              className="btn-primary mt-3"
              onClick={() => setRetry((n) => n + 1)}
              disabled={retrying}
            >
              <RefreshCw size={15} className={retrying ? "animate-spin" : ""} />
              {retrying ? "正在重连…" : "重试连接"}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

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
            <QuickLink to="/jds" title="在招岗位" desc="抓取 / 筛选岗位，也可粘贴 JD 结构化" icon={BriefcaseBusiness} number="02" />
            <QuickLink to="/customizations" title="定制化" desc="差距分析 · 定制简历 · 面试押题" icon={Sparkles} number="03" />
            <QuickLink to="/settings" title="模型管理" desc="配置默认 LLM Provider" icon={Server} number="04" />
          </div>
        </section>

        <section className="card">
          <p className="eyebrow">LIBRARY</p>
          <h2 className="text-xl font-bold mb-1">资料库</h2>
          <p className="text-sm text-slate-500 mb-4">本地数据库里的真实数量</p>
          {!stats && <p className="text-sm text-slate-400">加载中…</p>}
          {stats && (
            <div className="grid grid-cols-2 gap-3">
              <MiniStat icon={FileText} label="简历" value={`${stats.resumes} 份`} hint="已上传解析" />
              <MiniStat
                icon={BriefcaseBusiness}
                label="在招岗位"
                value={`${stats.jobs} 条`}
                hint={`${stats.jobsWithSalary} 条有薪资`}
              />
              <MiniStat
                icon={Sparkles}
                label="定制化"
                value={`${stats.customizationsDone} / ${stats.customizations}`}
                hint="已完成 / 全部"
              />
              <MiniStat
                icon={Server}
                label="模型"
                value={`${stats.providers} 个`}
                hint={stats.providers > 0 ? "含 mock" : "未配置"}
              />
            </div>
          )}
        </section>
      </div>

      <section className="border-t pt-6"><p className="eyebrow">GET STARTED</p><h2 className="text-xl font-bold mb-3">推荐使用顺序</h2><ol className="grid md:grid-cols-5 gap-3 text-sm text-slate-600">
        <li>「模型管理」可以先用默认 mock——离线可用；想要语义级分析再配真实 Key</li>
        <li>「简历管理」上传简历 → 自动拆解成可编辑文本 → 改完直接导出</li>
        <li>「在招岗位」抓取或筛选岗位，也可以粘贴 JD 文本 → 自动结构化</li>
        <li>「定制化」搜索选一条岗位 + 选简历 → 发起，得到差距分析与押题</li>
        <li>在报告里看 匹配度 / 缺失技能 / 定制简历 / 押题，并导出 PDF</li>
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

function MiniStat({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: typeof FileText;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border bg-slate-50/70 px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-xs text-slate-500">
        <Icon size={13} className="text-brand-600" />
        {label}
      </div>
      <div className="text-lg font-bold text-slate-800 leading-6 mt-0.5">{value}</div>
      {hint && <div className="text-[11px] text-slate-400">{hint}</div>}
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
