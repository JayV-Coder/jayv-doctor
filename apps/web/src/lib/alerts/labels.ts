// Tela 20 (Alertas, #41): textos dos cards de Regra e a chave VAPID para o navegador.

type Conditions = {
  type?: unknown;
  min_severity?: unknown;
  environments?: unknown;
  integrations?: unknown;
  threshold_pct?: unknown;
  minutes?: unknown;
};

const SEVERITY: Record<string, string> = {
  critical: "crítico",
  high: "alta ou mais",
  medium: "média ou mais",
  low: "qualquer severidade",
};
const CHANNEL: Record<string, string> = {
  webpush: "Push",
  email: "E-mail",
  slack: "Slack",
  teams: "Microsoft Teams",
  jira: "Jira",
};

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function scope(ids: string[], integrations: { id: string; name: string }[]): string {
  const names = ids.map((id) => integrations.find((item) => item.id === id)?.name ?? "Integração");
  return names.length > 0 ? names.join(", ") : "todas as Integrações";
}

export function ruleWhen(
  conditions: Conditions,
  integrations: { id: string; name: string }[],
): string {
  switch (conditions.type) {
    case "incident": {
      const severity = SEVERITY[String(conditions.min_severity)] ?? String(conditions.min_severity);
      const environments = list(conditions.environments);
      return `${severity} · ${environments.length > 0 ? environments.join(", ") : "todos os Ambientes"}`;
    }
    case "error_rate":
      return `erro > ${String(conditions.threshold_pct)}% em ${String(conditions.minutes)} min · ${scope(list(conditions.integrations), integrations)}`;
    case "connector_failing":
      return "Conector em falha";
    default:
      return `Diagnóstico sem revisão há ${String(conditions.minutes)} min`;
  }
}

export function ruleSend(ids: string[], channels: { id: string; type: string }[]): string {
  const kinds = [
    ...new Set(
      ids.flatMap((id) => {
        const found = channels.find((item) => item.id === id);
        return found ? [found.type] : [];
      }),
    ),
  ];
  const order = Object.keys(CHANNEL);
  kinds.sort((a, b) => order.indexOf(a) - order.indexOf(b));
  return kinds.length > 0 ? kinds.map((kind) => CHANNEL[kind] ?? kind).join(", ") : "nenhum canal";
}

export type Quiet = { start?: string; end?: string } | null;

export function quietText(quiet: Quiet | undefined): string {
  if (!quiet?.start || !quiet.end) return "sem silêncio";
  return `${quiet.start} às ${quiet.end}, exceto severidade crítica`;
}

// Da API (`quiet_hours` livre) para os dois horários que a tela mostra.
export function toQuiet(raw: Record<string, unknown> | null | undefined): Quiet {
  const start = raw?.start;
  const end = raw?.end;
  return typeof start === "string" && typeof end === "string" ? { start, end } : null;
}

// `applicationServerKey` do PushManager: a chave pública VAPID em base64url, como bytes.
export function applicationServerKey(key: string): Uint8Array<ArrayBuffer> {
  const padded = key.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (key.length % 4)) % 4);
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
  return bytes;
}
