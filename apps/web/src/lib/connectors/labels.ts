import type { ChipTone } from "@/components/ui/chip";
import { formatNumber } from "../format";

type Label = { label: string; tone: ChipTone };

// `failing` volta a `active` sozinho na próxima Sincronização que der certo; `paused` espera uma
// pessoa (docs/operations/conectores.md).
export function connectorState(connector: { status: string; last_sync_at: string | null }): Label {
  switch (connector.status) {
    case "failing":
      return { label: "Com falhas", tone: "warning" };
    case "paused":
      return { label: "Pausado", tone: "neutral" };
    case "disabled":
      return { label: "Desativado", tone: "danger" };
    default:
      return connector.last_sync_at
        ? { label: "Saudável", tone: "success" }
        : { label: "Aguardando", tone: "info" };
  }
}

function minutesBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / 60_000);
}

function elapsed(instant: string, now: Date): string {
  const minutes = minutesBetween(new Date(instant), now);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${String(minutes)} min`;
  if (minutes < 48 * 60) return `há ${String(Math.floor(minutes / 60))} h`;
  return `há ${String(Math.floor(minutes / (24 * 60)))} d`;
}

export function lastSyncText(
  connector: { last_sync_at: string | null; last_sync_records: number | null },
  now: Date,
): string {
  if (!connector.last_sync_at) return "ainda não sincronizou";
  const records = connector.last_sync_records ?? 0;
  return `${elapsed(connector.last_sync_at, now)} · ${formatNumber(records)} ${records === 1 ? "evento" : "eventos"}`;
}

// O formato do Checkpoint é do provedor; o instante, quando há, é o que interessa a quem opera.
export function checkpointText(checkpoint: Record<string, unknown> | null | undefined): string {
  if (!checkpoint) return "ainda não há";
  // Salesforce (#37): um ponto por fonte; mostra o mais recente.
  const sources = checkpoint.sources as Record<string, { at?: unknown }> | undefined;
  const latest =
    sources &&
    Object.values(sources)
      .map((mark) => (typeof mark.at === "string" ? mark.at : ""))
      .sort()
      .at(-1);
  const stamp = latest || checkpoint.timestamp;
  const instant = typeof stamp === "string" ? new Date(stamp) : null;
  if (!instant || Number.isNaN(instant.getTime())) return "gravado";
  return `${instant.toISOString().slice(0, 19).replace("T", " ")}Z`;
}

export function nextRunText(nextRunAt: string, now: Date): string {
  const minutes = minutesBetween(now, new Date(nextRunAt));
  if (minutes < 1) return "agora";
  if (minutes < 60) return `em ${String(minutes)} min`;
  return `em ${String(Math.round(minutes / 60))} h`;
}

export function pauseText(reason: string | null | undefined): string {
  if (reason === "auth") {
    return "Pausado: o provedor recusou a credencial. Envie uma credencial nova para retomar.";
  }
  if (reason === "api_limit") {
    return "Aguardando: o limite diário da API do provedor chegou a 80%. A coleta volta sozinha na janela seguinte.";
  }
  return "Pausado por um Owner ou Admin.";
}

export function syncDuration(startedAt: string, finishedAt: string | null): string {
  if (!finishedAt) return "em andamento";
  const seconds = Math.round(
    (new Date(finishedAt).getTime() - new Date(startedAt).getTime()) / 1000,
  );
  if (seconds < 60) return `${String(seconds)} s`;
  return `${String(Math.floor(seconds / 60))} min ${String(seconds % 60)} s`;
}

const SYNC: Record<string, Label> = {
  succeeded: { label: "Concluída", tone: "success" },
  failed: { label: "Falhou", tone: "danger" },
  running: { label: "Rodando", tone: "info" },
};

export function syncStatus(status: string): Label {
  return SYNC[status] ?? { label: status, tone: "neutral" };
}

export function intervalLabel(seconds: number): string {
  return seconds % 3600 === 0
    ? `a cada ${String(seconds / 3600)} h`
    : `a cada ${String(Math.round(seconds / 60))} min`;
}

// Intervalos oferecidos na tela; a API aceita de 60 s a 1 dia.
export const INTERVALS = [60, 300, 900, 3600] as const;
