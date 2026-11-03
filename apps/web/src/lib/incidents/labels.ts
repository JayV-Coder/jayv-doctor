import type { ChipTone } from "@/components/ui/chip";

export function incidentCode(number: number): string {
  return `INC-${String(number).padStart(4, "0")}`;
}

const SEVERITY: Record<string, { label: string; tone: ChipTone }> = {
  critical: { label: "Crítico", tone: "danger" },
  high: { label: "Alto", tone: "danger" },
  medium: { label: "Médio", tone: "warning" },
  low: { label: "Baixo", tone: "neutral" },
};

export const SEVERITIES = ["critical", "high", "medium", "low"] as const;

export function severityLabel(severity: string): string {
  return SEVERITY[severity]?.label ?? severity;
}

export function severityTone(severity: string): ChipTone {
  return SEVERITY[severity]?.tone ?? "neutral";
}

const STATUS: Record<string, string> = {
  open: "Aberto",
  investigating: "Em análise",
  resolved: "Resolvido",
  dismissed: "Descartado",
};

export const STATUSES = ["open", "investigating", "resolved", "dismissed"] as const;
export type IncidentStatus = (typeof STATUSES)[number];

export function statusLabel(status: string): string {
  return STATUS[status] ?? status;
}

// Espelho de doctor.check_incident_transition: a tela só oferece o que o banco aceita.
export const NEXT_STATUSES: Record<IncidentStatus, IncidentStatus[]> = {
  open: ["investigating", "resolved", "dismissed"],
  investigating: ["open", "resolved", "dismissed"],
  resolved: ["open"],
  dismissed: ["open"],
};

export function ageText(iso: string, now: Date): string {
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 60_000));
  if (minutes < 60) return `${String(minutes)} min`;
  if (minutes < 48 * 60) return `${String(Math.floor(minutes / 60))} h`;
  return `${String(Math.floor(minutes / (24 * 60)))} d`;
}
