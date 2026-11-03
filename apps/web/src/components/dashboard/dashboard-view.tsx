import Link from "next/link";
import { Chip } from "@/components/ui/chip";
import { KpiTile } from "@/components/ui/kpi-tile";
import type { Dashboard } from "@/lib/dashboard/api";
import { changeText, mttrText, rateText } from "@/lib/dashboard/labels";
import { formatNumber } from "@/lib/format";
import {
  ageText,
  incidentCode,
  severityLabel,
  severityTone,
  statusLabel,
} from "@/lib/incidents/labels";
import { environmentLabel } from "@/lib/integrations/labels";
import { CategoryBars } from "./category-bars";
import { FailuresChart } from "./failures-chart";

const PERIOD_LABELS: Record<string, string> = { "24h": "24 h", "7d": "7 dias", "30d": "30 dias" };
const ENVIRONMENTS = [
  ["prd", "Produção"],
  ["hml", "Homologação"],
  ["dev", "Desenvolvimento"],
] as const;

function href(period: string, environment: string | null): string {
  const params = new URLSearchParams();
  if (period !== "24h") params.set("periodo", period);
  if (environment) params.set("ambiente", environment);
  const text = params.toString();
  return text ? `/?${text}` : "/";
}

export function DashboardView({
  board,
  period,
  environment,
}: {
  board: Dashboard;
  period: string;
  environment: string | null;
}) {
  const now = new Date();
  const previous = period === "24h" ? "vs. 24 h anteriores" : "vs. período anterior";
  const critical = board.critical_incident;
  return (
    <>
      <div className="row-wrap" aria-label="Período e Ambiente">
        {Object.entries(PERIOD_LABELS).map(([value, label]) => (
          <Link
            key={value}
            className="chip-link"
            aria-pressed={period === value}
            href={href(value, environment)}
          >
            {label}
          </Link>
        ))}
        {ENVIRONMENTS.map(([value, label]) => (
          <Link
            key={value}
            className="chip-link"
            aria-pressed={environment === value}
            href={href(period, environment === value ? null : value)}
          >
            {label}
          </Link>
        ))}
      </div>

      {critical && (
        <Link className="card incident-card critical" href={`/incidentes/${critical.id}`}>
          <span className="row-between">
            <span className="small">
              {incidentCode(critical.number)} · {statusLabel(critical.status).toLowerCase()} há{" "}
              {ageText(critical.last_seen_at, now)}
            </span>
            <Chip tone={severityTone(critical.severity)}>{severityLabel(critical.severity)}</Chip>
          </span>
          <span className="t">{critical.title}</span>
          <span className="small">
            {critical.integration_name} · {environmentLabel(critical.environment)}
          </span>
        </Link>
      )}

      <div className="kpis">
        <KpiTile
          label="Execuções"
          value={formatNumber(board.executions.value ?? 0)}
          detail={changeText(board.executions.change, previous)}
        />
        <KpiTile
          label="Taxa de erro"
          value={rateText(board.error_rate.value)}
          detail={changeText(board.error_rate.change, previous)}
        />
        <KpiTile label="Incidentes abertos" value={formatNumber(board.open_incidents)} />
        <KpiTile
          label="MTTR"
          value={mttrText(board.mttr_minutes.value)}
          detail={
            board.mttr_vs_baseline !== null
              ? changeText(board.mttr_vs_baseline, "vs. baseline")
              : changeText(board.mttr_minutes.change, previous)
          }
        />
      </div>

      <div className="dashboard-charts">
        <FailuresChart buckets={board.failures} bucket={board.bucket} />
        <CategoryBars items={board.failures_by_category} />
      </div>

      {board.recent_incidents.length > 0 && (
        <section className="desktop-only" aria-labelledby="recentes">
          <h2 id="recentes" className="label">
            Incidentes recentes
          </h2>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Incidente</th>
                <th scope="col">Severidade</th>
                <th scope="col">Status</th>
                <th scope="col">Integração</th>
                <th scope="col">Execuções</th>
              </tr>
            </thead>
            <tbody>
              {board.recent_incidents.map((incident) => (
                <tr key={incident.id}>
                  <td>
                    <Link href={`/incidentes/${incident.id}`}>
                      {incidentCode(incident.number)} · {incident.title}
                    </Link>
                  </td>
                  <td>{severityLabel(incident.severity)}</td>
                  <td>{statusLabel(incident.status)}</td>
                  <td>{incident.integration_name}</td>
                  <td>{formatNumber(incident.execution_count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <p className="muted small">
        Atualizado a cada 10 min · horários em UTC
        {board.mttr_baseline_minutes
          ? ` · baseline do MTTR ${mttrText(board.mttr_baseline_minutes)}`
          : ""}
      </p>
    </>
  );
}
