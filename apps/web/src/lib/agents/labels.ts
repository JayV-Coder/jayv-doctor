import type { ChipTone } from "@/components/ui/chip";

type Label = { label: string; tone: ChipTone };

// O agente manda sinal de vida a cada rodada (5 min por padrão); três rodadas sem sinal já é
// motivo para olhar a máquina do cliente.
const SILENT_MINUTES = 15;

function minutesSince(instant: string, now: Date): number {
  return Math.round((now.getTime() - new Date(instant).getTime()) / 60_000);
}

export function agentState(
  agent: { status: string; last_seen_at: string | null; registration_expires_at: string | null },
  now: Date,
): Label {
  switch (agent.status) {
    case "revoked":
      return { label: "Revogado", tone: "danger" };
    case "pending":
      return agent.registration_expires_at && new Date(agent.registration_expires_at) > now
        ? { label: "Aguardando registro", tone: "info" }
        : { label: "Token vencido", tone: "warning" };
    default:
      return agent.last_seen_at && minutesSince(agent.last_seen_at, now) <= SILENT_MINUTES
        ? { label: "Conectado", tone: "success" }
        : { label: "Sem contato", tone: "warning" };
  }
}

export function lastSeenText(instant: string | null, now: Date): string {
  if (!instant) return "nunca falou com a plataforma";
  const minutes = minutesSince(instant, now);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${String(minutes)} min`;
  if (minutes < 48 * 60) return `há ${String(Math.floor(minutes / 60))} h`;
  return `há ${String(Math.floor(minutes / (24 * 60)))} d`;
}

type Collection = { type?: unknown; path?: unknown; table?: unknown; name?: unknown };

export function collectionsText(config: { collections?: unknown }): string {
  const collections = Array.isArray(config.collections) ? (config.collections as Collection[]) : [];
  if (collections.length === 0) return "nenhuma coleta autorizada";
  return collections
    .map((item) => {
      if (item.type === "directory") return `pasta ${String(item.path)}`;
      if (item.type === "rfc_table") return `tabela ${String(item.table)}`;
      return `função ${String(item.name)}`;
    })
    .join(" · ");
}
