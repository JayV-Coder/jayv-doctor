import type { ChipTone } from "@/components/ui/chip";
import { formatNumber } from "../format";

const STATUS: Record<string, { label: string; tone: ChipTone }> = {
  failed: { label: "Falhou", tone: "danger" },
  success: { label: "Sucesso", tone: "success" },
  pending_confirmation: { label: "Pendente de confirmação", tone: "warning" },
  unknown: { label: "Indeterminada", tone: "neutral" },
};

export const STATUSES = ["failed", "success", "pending_confirmation", "unknown"] as const;

export function statusLabel(status: string): string {
  return STATUS[status]?.label ?? status;
}

export function statusTone(status: string): ChipTone {
  return STATUS[status]?.tone ?? "neutral";
}

const decimal = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function durationText(ms: number): string {
  if (ms < 1000) return `${formatNumber(ms)} ms`;
  if (ms < 60_000) return `${decimal.format(Math.floor(ms / 100) / 10)} s`;
  const seconds = Math.round(ms / 1000);
  return `${String(Math.floor(seconds / 60))} min ${String(seconds % 60)} s`;
}

// Em UTC: os Eventos chegam de sistemas em fusos diferentes, e a Timeline compara instantes.
export function timeOfDay(iso: string): string {
  return new Date(iso).toISOString().slice(11, 23);
}

export function executionTitle(id: string, keys: Record<string, string[] | undefined>): string {
  const parts = [keys.execution_id?.[0], keys.trace_id?.[0]].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : `Execução ${id.slice(0, 8)}`;
}

const STRATEGIES: Record<string, string> = {
  execution_id: "por execution_id",
  trace_id: "por trace_id",
  cross_system: "pelo Mapa entre sistemas",
  business_reference: "pela Referência",
  temporal_proximity: "por proximidade (fraca)",
};

export function correlatedByLabel(strategy: string | null | undefined): string {
  return strategy ? (STRATEGIES[strategy] ?? strategy) : "sem correlação";
}

export function severityTone(severity: string): ChipTone {
  if (severity === "ERROR" || severity === "CRITICAL") return "danger";
  if (severity === "WARNING") return "warning";
  return "neutral";
}

// O que cada detector da Sanitização (packages/security) tira, em português.
const KINDS: Record<string, [string, string]> = {
  bearer: ["token Bearer removido", "tokens Bearer removidos"],
  jwt: ["JWT removido", "JWTs removidos"],
  token: ["token removido", "tokens removidos"],
  authorization: ["cabeçalho de autorização removido", "cabeçalhos de autorização removidos"],
  cookie: ["cookie removido", "cookies removidos"],
  password: ["senha ou segredo removido", "senhas ou segredos removidos"],
  private_key: ["chave privada removida", "chaves privadas removidas"],
  salesforce_session: ["sessão do Salesforce removida", "sessões do Salesforce removidas"],
  aws_key: ["chave da AWS removida", "chaves da AWS removidas"],
  gcp_key: ["chave do Google Cloud removida", "chaves do Google Cloud removidas"],
  gcp_token: ["token do Google Cloud removido", "tokens do Google Cloud removidos"],
  cpf: ["CPF removido", "CPFs removidos"],
  cnpj: ["CNPJ removido", "CNPJs removidos"],
  email: ["e-mail removido", "e-mails removidos"],
  telefone: ["telefone removido", "telefones removidos"],
  cartao: ["cartão removido", "cartões removidos"],
  ip: ["IP removido", "IPs removidos"],
};

export function sanitizationLines(
  report: { counts?: Record<string, number>; truncated?: boolean } | null | undefined,
): string[] {
  const counts = report?.counts ?? {};
  const lines = Object.entries(counts)
    .filter(([kind, count]) => kind !== "referencia" && count > 0)
    .map(([kind, count]) => {
      const [one, many] = KINDS[kind] ?? ["dado sensível removido", "dados sensíveis removidos"];
      return `${formatNumber(count)} ${count === 1 ? one : many}`;
    });
  const references = counts.referencia ?? 0;
  if (references > 0) {
    lines.push(
      `${formatNumber(references)} ${references === 1 ? "Referência de negócio" : "Referências de negócio"} em HMAC`,
    );
  }
  if (lines.length === 0) lines.push("Nada sensível encontrado");
  if (report?.truncated) lines.push("Conteúdo longo truncado");
  return lines;
}

export type JsonToken = {
  kind: "plain" | "key" | "string" | "number" | "literal" | "redacted";
  text: string;
};

const TOKEN =
  /("(?:[^"\\]|\\.)*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b/g;

// Realce simples para a Tela 9: o JSON vem do próprio `JSON.stringify`, então a gramática é
// a dele, sem casos estranhos. O que a Sanitização trocou fica marcado.
export function highlightJson(value: unknown): JsonToken[] {
  const source = JSON.stringify(value, null, 2);
  const tokens: JsonToken[] = [];
  let last = 0;
  const plain = (text: string) => {
    if (!text) return;
    const previous = tokens.at(-1);
    if (previous?.kind === "plain") previous.text += text;
    else tokens.push({ kind: "plain", text });
  };
  for (const match of source.matchAll(TOKEN)) {
    plain(source.slice(last, match.index));
    const [whole, text, colon, number, literal] = match;
    if (text !== undefined && colon !== undefined) {
      tokens.push({ kind: "key", text });
      plain(colon);
    } else if (text !== undefined) {
      tokens.push({ kind: text.startsWith('"[REMOVIDO:') ? "redacted" : "string", text });
    } else if (number !== undefined) {
      tokens.push({ kind: "number", text: number });
    } else if (literal !== undefined) {
      tokens.push({ kind: "literal", text: literal });
    }
    last = match.index + whole.length;
  }
  plain(source.slice(last));
  return tokens;
}

function text(value: unknown): string | null {
  return typeof value === "string" || typeof value === "number" ? String(value) : null;
}

// "sap-order-sync" ou, sem serviço, o provedor: de onde o Evento veio, em uma palavra.
export function eventSource(source: Record<string, unknown>): string {
  return text(source.service) ?? text(source.provider) ?? "origem desconhecida";
}

export function errorSummary(error: Record<string, unknown> | null | undefined): string | null {
  if (!error) return null;
  const status = text(error.http_status);
  const parts = [status && `HTTP ${status}`, text(error.category)].filter(Boolean);
  return parts.length > 0 ? parts.join(" ") : null;
}
