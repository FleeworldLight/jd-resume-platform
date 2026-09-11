import type { ReactNode } from "react";
import { ApiError } from "./api";
import { AlertCircle, CheckCircle2, Clock3, LoaderCircle } from "lucide-react";

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
