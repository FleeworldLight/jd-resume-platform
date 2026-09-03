import type { ReactNode } from "react";
import { ApiError } from "./api";

export function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "COMPLETED"
      ? "badge-completed"
      : status === "FAILED"
        ? "badge-failed"
        : status === "PROCESSING"
          ? "badge-processing"
          : "badge-pending";
  return <span className={cls}>{status}</span>;
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof ApiError ? error.message : String(error);
  return (
    <div className="card border-red-200 bg-red-50 text-red-700 mb-4 text-sm">
      ❌ {msg}
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
