import type { ReactNode } from "react";
import { ApiError } from "./api";
import { AlertCircle, CheckCircle2, Clock3, LoaderCircle } from "lucide-react";

/** 统一的页面头部：各页共用同一套视觉，避免各写各的。 */
export function PageHero({
  eyebrow,
  title,
  desc,
  children,
}: {
  eyebrow: string;
  title: string;
  desc?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="rounded-3xl bg-[#e4f4ef] border border-brand-100 p-6 sm:p-8 flex flex-col lg:flex-row lg:items-end gap-6">
      <div className="flex-1">
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 mb-2">{title}</h1>
        {desc && <div className="text-slate-600 max-w-xl leading-6">{desc}</div>}
      </div>
      {children && <div className="shrink-0">{children}</div>}
    </section>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "COMPLETED"
      ? "badge-completed"
      : status === "FAILED"
        ? "badge-failed"
        : status === "PROCESSING"
          ? "badge-processing"
          : "badge-pending";
  const Icon = status === "COMPLETED" ? CheckCircle2 : status === "FAILED" ? AlertCircle : status === "PROCESSING" ? LoaderCircle : Clock3;
  return <span className={cls}><Icon size={13} className={status === "PROCESSING" ? "animate-spin" : ""} />{status}</span>;
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof ApiError ? error.message : String(error);
  return (
    <div className="card border-red-200 bg-red-50/80 text-red-700 mb-4 text-sm flex items-start gap-2">
      <AlertCircle size={18} className="shrink-0 mt-0.5" /> <span>{msg}</span>
    </div>
  );
}

export function Card({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </div>
  );
}
