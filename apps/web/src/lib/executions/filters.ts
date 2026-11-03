import type { ExecutionSearch } from "@/lib/api";
import { ENVIRONMENTS as ENVIRONMENT_OPTIONS } from "@/lib/integrations/labels";
import { STATUSES as STATUS_LIST } from "./labels";

// Filtros que podem ir na URL (nada sensível): Integração, Ambiente, status e período. O termo de
// busca (`q`) nunca vai: pode ser um número de pedido.
export interface Filters {
  status?: string | undefined;
  integration?: string | undefined;
  environment?: string | undefined;
  period?: string | undefined;
}

type Search = Partial<ExecutionSearch>;

export const PERIODS = { "24h": 24, "7d": 24 * 7, "30d": 24 * 30 } as const;
const STATUSES = new Set<string>(STATUS_LIST);
const ENVIRONMENTS = new Set<string>(ENVIRONMENT_OPTIONS.map(({ value }) => value));
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function readFilters(params: Record<string, string | string[] | undefined>): Filters {
  const one = (key: string) => {
    const value = params[key];
    return typeof value === "string" ? value : undefined;
  };
  const status = one("status");
  const integration = one("integracao");
  const environment = one("ambiente");
  const period = one("periodo");
  return {
    status: status && STATUSES.has(status) ? status : undefined,
    integration: integration && UUID.test(integration) ? integration : undefined,
    environment: environment && ENVIRONMENTS.has(environment) ? environment : undefined,
    period: period && period in PERIODS ? period : undefined,
  };
}

// `now` é o instante da primeira página: as seguintes repetem o mesmo início, senão "Carregar
// mais" pularia o que ficou entre uma e outra.
export function toSearch(filters: Filters, now: Date): Search {
  const hours = filters.period ? PERIODS[filters.period as keyof typeof PERIODS] : undefined;
  return {
    status: (filters.status ?? null) as NonNullable<Search["status"]> | null,
    integration_id: filters.integration ?? null,
    environment: (filters.environment ?? null) as NonNullable<Search["environment"]> | null,
    from: hours ? new Date(now.getTime() - hours * 3_600_000).toISOString() : null,
  };
}

// Link de um chip: liga ou desliga um filtro, mantendo os outros.
export function toggleHref(filters: Filters, key: keyof Filters, value: string): string {
  const next: Filters = { ...filters, [key]: filters[key] === value ? undefined : value };
  const names: Record<keyof Filters, string> = {
    status: "status",
    integration: "integracao",
    environment: "ambiente",
    period: "periodo",
  };
  const query = new URLSearchParams();
  for (const [field, name] of Object.entries(names) as [keyof Filters, string][]) {
    const current = next[field];
    if (current) query.set(name, current);
  }
  const text = query.toString();
  return text ? `/execucoes?${text}` : "/execucoes";
}
