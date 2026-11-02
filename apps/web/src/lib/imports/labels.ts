import type { ChipTone } from "@/components/ui/chip";
import { formatNumber } from "../format";

export type ImportStatus = "pending" | "uploaded" | "processing" | "done" | "failed" | "rejected";

const LABELS: Record<ImportStatus, string> = {
  pending: "Enviando",
  uploaded: "Na fila",
  processing: "Normalizando",
  done: "Concluída",
  failed: "Falhou",
  rejected: "Recusada",
};

const TONES: Record<ImportStatus, ChipTone> = {
  pending: "neutral",
  uploaded: "neutral",
  processing: "info",
  done: "success",
  failed: "danger",
  rejected: "danger",
};

export function statusLabel(status: ImportStatus): string {
  return LABELS[status];
}

export function statusTone(status: ImportStatus): ChipTone {
  return TONES[status];
}

function count(value: number, one: string, many: string): string {
  return `${formatNumber(value)} ${value === 1 ? one : many}`;
}

export function importSummary(counts: {
  accepted: number;
  rejected: number;
  duplicates: number;
  secrets_removed: number;
}): string {
  return [
    count(counts.accepted, "evento", "eventos"),
    counts.rejected > 0 && count(counts.rejected, "rejeitada", "rejeitadas"),
    counts.duplicates > 0 && count(counts.duplicates, "duplicado", "duplicados"),
    counts.secrets_removed > 0 &&
      count(counts.secrets_removed, "segredo removido", "segredos removidos"),
  ]
    .filter(Boolean)
    .join(" · ");
}
