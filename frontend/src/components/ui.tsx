import type { ReactNode } from "react";

export function StatusBadge({ value }: { value: string }) {
  const normalized = value.toUpperCase();
  const tone =
    normalized.includes("COMPLETED") ||
    normalized.includes("APPROVED") ||
    normalized.includes("DELIVERED") ||
    normalized === "LOW"
      ? "success"
      : normalized.includes("FAILED") ||
          normalized.includes("REJECTED") ||
          normalized.includes("CANCELLED") ||
          normalized === "HIGH"
        ? "danger"
        : normalized.includes("PENDING") ||
            normalized.includes("AWAITING") ||
            normalized === "MEDIUM"
          ? "warning"
          : "neutral";
  return <span className={`status-badge ${tone}`}>{value.replaceAll("_", " ")}</span>;
}

export function MetricCard({
  label,
  value,
  detail,
  icon,
  tone = "green"
}: {
  label: string;
  value: ReactNode;
  detail: string;
  icon: string;
  tone?: "green" | "amber" | "blue" | "ink";
}) {
  return (
    <article className={`metric-card tone-${tone}`}>
      <div className="metric-icon" aria-hidden="true">{icon}</div>
      <div>
        <p className="metric-label">{label}</p>
        <strong className="metric-value">{value}</strong>
        <p className="metric-detail">{detail}</p>
      </div>
    </article>
  );
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <span aria-hidden="true">◇</span>
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

export function LoadingBlock({ label = "正在读取企业数据" }: { label?: string }) {
  return (
    <div className="loading-block" role="status">
      <span className="loading-dot" />
      <span>{label}</span>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function formatMoney(value: string | number | null, currency = "CNY") {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency,
    maximumFractionDigits: 0
  }).format(Number(value));
}

export function formatDate(value: string | null | undefined, withTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {})
  }).format(date);
}
