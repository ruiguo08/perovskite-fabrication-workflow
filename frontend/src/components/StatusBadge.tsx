export type StatusTone =
  | "neutral"
  | "active"
  | "planned"
  | "warning"
  | "danger"
  | "success";

const TONE_BY_STATUS: Record<string, StatusTone> = {
  active: "active",
  ready: "active",
  running: "active",
  in_progress: "active",
  released: "active",
  approved: "success",
  completed: "success",
  consumed: "success",
  pending: "warning",
  pending_approval: "warning",
  draft: "planned",
  planned: "planned",
  preparing: "planned",
  cancelled: "neutral",
  failed: "danger",
  error: "danger",
  critical: "danger",
  excluded: "neutral",
  inactive: "neutral",
  archived: "neutral",
  closed: "neutral",
};

export function toneForStatus(status: string): StatusTone {
  return TONE_BY_STATUS[status] ?? "neutral";
}

interface StatusBadgeProps {
  status: string;
  tone?: StatusTone;
}

/** Compact status chip. Tone is pure presentation; never the only signal. */
export function StatusBadge({ status, tone }: StatusBadgeProps) {
  const resolvedTone = tone ?? toneForStatus(status);
  return (
    <span className={`status-badge status-badge--${resolvedTone}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}