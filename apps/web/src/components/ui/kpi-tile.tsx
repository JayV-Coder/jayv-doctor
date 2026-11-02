import type { ReactNode } from "react";

export function KpiTile({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: ReactNode;
}) {
  return (
    <div className="kpi">
      <span className="label">{label}</span>
      <b>{value}</b>
      {detail && <span className="small">{detail}</span>}
    </div>
  );
}
