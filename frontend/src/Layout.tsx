import { useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { BriefcaseBusiness, FileText, Gauge, Settings, Sparkles } from "lucide-react";
import { api } from "./api";

const navItems = [
  { to: "/", label: "首页", icon: Gauge },
  { to: "/resumes", label: "简历管理", icon: FileText },
  { to: "/jds", label: "在招岗位", icon: BriefcaseBusiness },
  { to: "/customizations", label: "定制化", icon: Sparkles },
  { to: "/settings", label: "设置", icon: Settings },
];

export default function Layout() {
  // 演示站横幅：后端 DEMO_MODE=true 时明确告知访客哪些操作被关闭
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
    <div className="min-h-screen flex flex-col">
      {demoMode && (
        <div className="bg-amber-50 border-b border-amber-200 text-amber-800 text-xs px-4 py-2 text-center">
          <b>在线演示站</b>：数据为脱敏样例；<b>抓取岗位、上传简历、删除</b>等写操作已关闭。
          完整功能请克隆仓库本地运行（见 README）。
        </div>
      )}
      <header className="bg-white/90 backdrop-blur border-b sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex flex-wrap items-center gap-4 sm:gap-8">
          <Link to="/" className="flex items-center gap-2.5 font-bold text-lg tracking-tight text-brand-700 mr-auto">
            <span className="grid place-items-center w-9 h-9 rounded-xl bg-brand-600 text-white shadow-lg shadow-brand-600/20"><Sparkles size={18} /></span>
            <span>求职工作台</span>
          </Link>
          <nav className="flex gap-1 w-full sm:w-auto overflow-x-auto">
            {navItems.map((it) => (
              <NavLink
                key={it.to}
                to={it.to}
                end={it.to === "/"}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm whitespace-nowrap transition ${
                    isActive
                      ? "bg-brand-50 text-brand-700 font-medium"
                      : "text-gray-600 hover:bg-gray-100"
                  }`
                }
              >
                <it.icon size={16} />
                {it.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-8">
        <Outlet />
      </main>
      <footer className="text-center text-xs text-slate-400 py-6">
        JD Resume Platform · local-first workspace
      </footer>
    </div>
  );
}
