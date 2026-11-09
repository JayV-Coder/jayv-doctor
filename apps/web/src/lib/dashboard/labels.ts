import { formatPercent } from "../format";

export function mttrText(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—";
  const rounded = Math.round(minutes);
  if (rounded < 60) return `${String(rounded)} min`;
  return `${String(Math.floor(rounded / 60))}h${String(rounded % 60).padStart(2, "0")}`;
}

export function rateText(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? "sem Execuções" : formatPercent(rate);
}

// A seta diz a direção e o texto diz o quanto: a cor nunca é a única pista.
export function changeText(change: number | null | undefined, against: string): string | null {
  if (change === null || change === undefined) return null;
  const arrow = change > 0 ? "▲" : change < 0 ? "▼" : "=";
  return `${arrow} ${formatPercent(Math.abs(change)).replace(/,0%$/, "%")} ${against}`;
}

export function bucketLabel(iso: string, bucket: "hour" | "day"): string {
  const date = new Date(iso);
  if (bucket === "hour") return `${String(date.getUTCHours())}h`;
  return `${String(date.getUTCDate()).padStart(2, "0")}/${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function peak<T extends { failed: number }>(buckets: T[]): T | null {
  const top = buckets.reduce<T | null>(
    (best, item) => (item.failed > (best?.failed ?? 0) ? item : best),
    null,
  );
  return top;
}

const CATEGORIES: Record<string, string> = {
  TIMEOUT: "Timeout",
  AUTH: "Autenticação",
  RATE_LIMIT: "Limite de chamadas",
  VALIDATION: "Validação",
  BUSINESS_REJECTION: "Rejeição de negócio",
  DUPLICATE: "Duplicidade",
  PENDING_CONFIRMATION: "Sem confirmação",
  DIVERGENCE: "Divergência",
  SAP_LOCK: "Bloqueio no SAP",
  IDOC_ERROR: "IDoc não lançado",
  SAP_AUTHORIZATION: "Autorização SAP",
  MASTER_DATA: "Cadastro mestre",
  UNCLASSIFIED: "Sem classificação",
};

export function categoryLabel(category: string): string {
  return CATEGORIES[category] ?? category;
}
