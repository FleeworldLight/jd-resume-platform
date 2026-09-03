import { Link, NavLink, Outlet } from "react-router-dom";

const navItems = [
  { to: "/", label: "首页" },
  { to: "/resumes", label: "简历" },
  { to: "/jds", label: "JD" },
  { to: "/customizations", label: "定制化" },
  { to: "/settings", label: "设置" },
];

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center gap-8">
          <Link to="/" className="font-bold text-lg text-brand-700">
            🎯 JD 定制化求职助手
          </Link>
          <nav className="flex gap-1">
            {navItems.map((it) => (
              <NavLink
                key={it.to}
                to={it.to}
                end={it.to === "/"}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-sm ${
                    isActive
                      ? "bg-brand-50 text-brand-700 font-medium"
                      : "text-gray-600 hover:bg-gray-100"
                  }`
                }
              >
                {it.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-6">
        <Outlet />
      </main>
      <footer className="text-center text-xs text-gray-400 py-4">
        v0.1.0 · W4 build
      </footer>
    </div>
  );
}
