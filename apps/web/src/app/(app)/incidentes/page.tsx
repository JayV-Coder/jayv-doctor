import Link from "next/link";
import { LiveRefresh } from "@/components/live-refresh";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { searchIncidents } from "@/lib/incidents/api";
import { statusLabel } from "@/lib/incidents/labels";
import { IncidentList } from "./incident-list";

export const metadata = { title: "Incidentes · Integration AI Doctor" };

const STATUS_CHIPS = [
  ["open", "Abertos"],
  ["investigating", "Em análise"],
  ["resolved", "Resolvidos"],
] as const;

// Tela 5: chips de status (na URL) com contagem, busca na página e cards. A lista atualiza
// sozinha pelo Realtime.
export default async function IncidentsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const status = STATUS_CHIPS.some(([value]) => value === params.status)
    ? [String(params.status)]
    : [];
  const severity = params.severidade === "critical" ? ["critical"] : [];
  const filters = { status, severity };
  const page = await searchIncidents({
    status: status.length > 0 ? (status as ["open"]) : null,
    severity: severity.length > 0 ? (severity as ["critical"]) : null,
  });

  function href(change: { status?: string | null; severidade?: string | null }): string {
    const next = new URLSearchParams();
    const nextStatus = change.status === undefined ? status[0] : change.status;
    const nextSeverity = change.severidade === undefined ? severity[0] : change.severidade;
    if (nextStatus) next.set("status", nextStatus);
    if (nextSeverity) next.set("severidade", nextSeverity);
    const text = next.toString();
    return text ? `/incidentes?${text}` : "/incidentes";
  }

  return (
    <>
      <LiveRefresh table="incidents" />
      <div className="row-wrap" aria-label="Filtros rápidos">
        {STATUS_CHIPS.map(([value, label]) => (
          <Link
            key={value}
            className="chip-link"
            aria-pressed={status[0] === value}
            href={href({ status: status[0] === value ? null : value })}
          >
            {label} {page?.counts[value] ?? 0}
          </Link>
        ))}
        <Link
          className="chip-link"
          aria-pressed={severity[0] === "critical"}
          href={href({ severidade: severity[0] === "critical" ? null : "critical" })}
        >
          Críticos
        </Link>
      </div>
      {page === null && (
        <ErrorState title="Não foi possível carregar os Incidentes" action={<ReloadButton />}>
          O serviço não respondeu. Tente de novo em instantes.
        </ErrorState>
      )}
      {page && Object.keys(page.counts).length === 0 && (
        <EmptyState title="Nenhum Incidente">
          Incidentes nascem quando uma Regra determinística reconhece uma falha nas Execuções
          {status[0] ? ` (filtro: ${statusLabel(status[0]).toLowerCase()})` : ""}.
        </EmptyState>
      )}
      {page && Object.keys(page.counts).length > 0 && (
        <IncidentList key={JSON.stringify(filters)} filters={filters} initial={page} />
      )}
    </>
  );
}
