import Link from "next/link";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { listIntegrations, searchExecutions } from "@/lib/api";
import { PERIODS, readFilters, toSearch, toggleHref } from "@/lib/executions/filters";
import { STATUSES, statusLabel } from "@/lib/executions/labels";
import { ENVIRONMENTS } from "@/lib/integrations/labels";
import { Explorer } from "./explorer";

export const metadata = { title: "Execuções · Integration AI Doctor" };

const PERIOD_LABELS: Record<keyof typeof PERIODS, string> = {
  "24h": "Últimas 24 h",
  "7d": "Últimos 7 dias",
  "30d": "Últimos 30 dias",
};

// Tela 7: os filtros não sensíveis ficam na URL (dá para compartilhar o link); a busca por termo
// fica na página, fora da URL.
export default async function ExecutionsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const filters = readFilters(await searchParams);
  const now = new Date();
  const [page, integrations] = await Promise.all([
    searchExecutions(toSearch(filters, now)),
    listIntegrations(),
  ]);
  const filtered = Object.values(filters).some(Boolean);

  return (
    <>
      <div className="row-wrap" aria-label="Filtros rápidos">
        <Link
          className="chip-link"
          aria-pressed={filters.status === "failed"}
          href={toggleHref(filters, "status", "failed")}
        >
          Falhas
        </Link>
        <Link
          className="chip-link"
          aria-pressed={filters.environment === "prd"}
          href={toggleHref(filters, "environment", "prd")}
        >
          Produção
        </Link>
        <Link
          className="chip-link"
          aria-pressed={filters.period === "24h"}
          href={toggleHref(filters, "period", "24h")}
        >
          24 h
        </Link>
        <BottomSheet title="Filtros" trigger="Filtros" triggerClassName="chip-link">
          <form className="stack" action="/execucoes">
            <label className="field">
              Integração
              <select name="integracao" defaultValue={filters.integration ?? ""}>
                <option value="">Todas</option>
                {integrations?.map((integration) => (
                  <option key={integration.id} value={integration.id}>
                    {integration.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="grid2">
              <label className="field">
                Ambiente
                <select name="ambiente" defaultValue={filters.environment ?? ""}>
                  <option value="">Todos</option>
                  {ENVIRONMENTS.map(({ value, label }) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Status
                <select name="status" defaultValue={filters.status ?? ""}>
                  <option value="">Todos</option>
                  {STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {statusLabel(status)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="field">
              Período
              <select name="periodo" defaultValue={filters.period ?? ""}>
                <option value="">Qualquer</option>
                {Object.entries(PERIOD_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <button className="btn primary" type="submit">
              Aplicar filtros
            </button>
            {filtered && (
              <Link className="btn" href="/execucoes">
                Limpar
              </Link>
            )}
          </form>
        </BottomSheet>
      </div>

      {page === null && (
        <ErrorState title="Não foi possível carregar as Execuções" action={<ReloadButton />}>
          O serviço não respondeu. Tente de novo em instantes.
        </ErrorState>
      )}
      {page?.items.length === 0 && !filtered ? (
        <EmptyState title="Nenhuma Execução recebida">
          Cada Execução reúne os Eventos de uma transação de ponta a ponta, vindos dos Conectores ou
          de uma Importação manual.
        </EmptyState>
      ) : (
        page && (
          <Explorer
            key={JSON.stringify(filters)}
            filters={filters}
            initial={page}
            since={now.toISOString()}
          />
        )
      )}
    </>
  );
}
