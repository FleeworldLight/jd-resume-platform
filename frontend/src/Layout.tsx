import { useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import {
  BriefcaseBusiness,
  FileText,
  Gauge,
  Github,
  Settings,
  Sparkles,
} from "lucide-react";
import { api } from "./api";

const GITHUB_URL = "https://github.com/FleeworldLight/jd-resume-platform";

// 左侧栏导航：分组 + 图标，选中态用「白底 + 细描边」
const NAV_GROUPS = [
  {
    title: "工作流",
    items: [
      { to: "/", label: "首页", icon: Gauge, end: true },
      { to: "/resumes", label: "简历管理", icon: FileText, end: false },
      { to: "/jds", label: "在招岗位", icon: BriefcaseBusiness, end: false },
      { to: "/customizations", label: "定制化", icon: Sparkles, end: false },
    ],
  },
  {
    title: "系统",
    items: [{ to: "/settings", label: "设置", icon: Settings, end: false }],
  },
];

export default function Layout() {
  // 演示站横幅：后端/静态演示的 /health 里 demo_mode=true 时显示
  const [demoMode, setDemoMode] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .get<{ demo_mode?: boolean }>("/health")
      .then((h) => {
        if (alive) setDemoMode(Boolean(h?.demo_mode));
      })
      .catch(() => {
        /* 后端没起也不影响浏览 */
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="min-h-screen bg-surface-low">
      {/* ---------- 左侧固定栏（lg 以上） ---------- */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-line bg-surface-low px-4 py-6 lg:flex">
        <Link to="/" className="mb-8 flex items-center gap-2.5 px-2">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-600 text-white shadow-lg shadow-brand-600/20">
            <Sparkles size={18} />
          </span>
          <span className="leading-tight">
            <span className="block font-serif text-[17px] font-semibold tracking-tight text-slate-900">
              求职工作台
            </span>
            <span className="block text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">
              JD RESUME
            </span>
          </span>
        </Link>

        <nav className="flex flex-1 flex-col gap-7 overflow-y-auto">
          {NAV_GROUPS.map((group) => (
            <div key={group.title}>
              <p className="nav-group-title mb-2">{group.title}</p>
              <div className="flex flex-col gap-1">
                {group.items.map((it) => (
                  <NavLink
                    key={it.to}
                    to={it.to}
                    end={it.end}
                    className={({ isActive }) =>
                      `nav-item ${isActive ? "nav-item-active" : ""}`
                    }
                  >
                    <it.icon size={17} className="shrink-0" />
                    {it.label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="mt-6 border-t border-line pt-4 text-[11px] leading-relaxed text-slate-400">
          <p>本地优先：数据存 SQLite</p>
          <p>默认 mock，离线可用</p>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-flex items-center gap-1.5 text-slate-500 hover:text-brand-700"
          >
            <Github size={13} />
            查看源码
          </a>
        </div>
      </aside>

      {/* ---------- 右侧区域 ---------- */}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-line bg-surface/85 backdrop-blur">
          {demoMode && (
            <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs text-amber-800 lg:px-10">
              <b>在线演示站</b>：数据为脱敏样例；
              <b>抓取岗位、上传简历、删除</b>等写操作已关闭。完整功能请克隆仓库本地运行。
            </div>
          )}

          <div className="flex items-center gap-3 px-4 py-3 lg:px-10">
            {/* 窄屏：品牌 + 横向滚动导航（侧栏在 lg 以下隐藏） */}
            <Link
              to="/"
              className="flex items-center gap-2 font-serif text-base font-semibold text-slate-900 lg:hidden"
            >
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white">
                <Sparkles size={15} />
              </span>
              求职工作台
            </Link>

            <nav className="flex gap-1 overflow-x-auto lg:hidden">
              {NAV_GROUPS.flatMap((g) => g.items).map((it) => (
                <NavLink
                  key={it.to}
                  to={it.to}
                  end={it.end}
                  className={({ isActive }) =>
                    `flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm transition ${
                      isActive
                        ? "bg-brand-50 font-medium text-brand-700"
                        : "text-slate-600 hover:bg-surface-mid"
                    }`
                  }
                >
                  <it.icon size={15} />
                  {it.label}
                </NavLink>
              ))}
            </nav>

            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noreferrer"
              className="ml-auto hidden items-center gap-1.5 text-xs text-slate-500 transition hover:text-brand-700 lg:inline-flex"
            >
              <Github size={14} />
              GitHub
            </a>
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl px-4 py-8 lg:px-10">
          <Outlet />
        </main>

        <footer className="border-t border-line py-6 text-center text-xs text-slate-400">
          JD Resume Platform · 本地优先的求职工作台
        </footer>
      </div>
    </div>
  );
}
