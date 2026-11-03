import type { ChipTone } from "../../components/ui/chip";
import { confidenceDecimal } from "../format";

const STATUS: Record<string, { text: string; tone: ChipTone }> = {
  queued: { text: "Na fila", tone: "info" },
  running: { text: "Em andamento", tone: "info" },
  published: { text: "Publicado", tone: "success" },
  inconclusive: { text: "Inconclusivo", tone: "neutral" },
  failed_llm: { text: "Só Regras (IA falhou)", tone: "warning" },
  failed: { text: "Falhou", tone: "danger" },
};

export function statusChip(diagnosis: { status: string; requires_human_review: boolean }): {
  text: string;
  tone: ChipTone;
} {
  // "Aceito" e "Corrigido" chegam com a revisão humana (#26).
  if (diagnosis.status === "published" && diagnosis.requires_human_review) {
    return { text: "Requer revisão", tone: "warning" };
  }
  return STATUS[diagnosis.status] ?? { text: diagnosis.status, tone: "neutral" };
}

export function statusText(status: string): string {
  return STATUS[status]?.text ?? status;
}

export function active(status: string): boolean {
  return status === "queued" || status === "running";
}

const STAGES = [
  ["validation", "Validando"],
  ["correlation", "Correlacionando"],
  ["rules", "Aplicando Regras"],
  ["knowledge", "Consultando base"],
  ["llm", "Interpretando"],
  ["verification", "Verificando Evidências"],
] as const;

export type Step = { label: string; state: "done" | "current" | "todo" };

// Só as etapas que vão rodar: sem IA, nem Base nem LLM; híbrido sem a Base, sem "Consultando base".
export function stageSteps(stage: string, mode: string, knowledge = true): Step[] {
  const stages = STAGES.filter(([key]) => {
    if (key === "llm") return mode === "hybrid";
    if (key === "knowledge") return mode === "hybrid" && knowledge;
    return true;
  });
  const current = stages.findIndex(([key]) => key === stage);
  return stages.map(([, label], index) => ({
    label,
    state: current < 0 ? "todo" : index < current ? "done" : index === current ? "current" : "todo",
  }));
}

export function modeLabel(mode: string): string {
  return mode === "hybrid" ? "híbrido" : "só Regras";
}

export function confidenceText(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : confidenceDecimal(value);
}

const SYSTEMS: Record<string, string> = {
  sap: "SAP",
  salesforce: "Salesforce",
  gcp: "Google Cloud",
  other: "Outro",
};

export function systemLabel(system: string | null | undefined): string {
  return system ? (SYSTEMS[system] ?? system) : "Indeterminado";
}

type EvidenceLink = {
  kind: "event" | "raw_log" | "chunk" | "global_chunk" | "rule_match";
  label: string;
  event_id: string | null;
  event_timestamp: string | null;
  execution_id: string | null;
};

export function evidenceChip(item: Pick<EvidenceLink, "kind" | "label">): string {
  if (item.kind === "rule_match") return item.label.split(" · ")[0] ?? "Regra";
  if (item.kind === "event") return "Evento";
  if (item.kind === "raw_log") return "Log";
  return "Base";
}

// Da Evidência ao JSON do Evento num toque; a Base abre a aba certa.
export function evidenceHref(item: EvidenceLink): string | null {
  if (item.kind === "chunk") return "/conhecimento";
  if (item.kind === "global_chunk") return "/conhecimento?aba=global";
  if (item.event_id) {
    // O instante leva a consulta direto à partição do Evento (também o da Regra, quando há).
    const at = item.event_timestamp;
    return `/eventos/${item.event_id}${at ? `?em=${encodeURIComponent(at)}` : ""}`;
  }
  return item.execution_id ? `/execucoes/${item.execution_id}` : null;
}

type Comparable = {
  version: number;
  status: string;
  classification: string | null;
  confidence: number | null;
  responsible_system: string | null;
  probable_cause: string | null;
};

export function changes(before: Comparable, after: Comparable): string[] {
  const found: string[] = [];
  if (before.status !== after.status) {
    found.push(`Status: ${statusText(before.status)} → ${statusText(after.status)}`);
  }
  if (before.classification !== after.classification) {
    found.push(`Classificação: ${before.classification ?? "—"} → ${after.classification ?? "—"}`);
  }
  if (before.confidence !== after.confidence) {
    found.push(
      `Confiança heurística: ${confidenceText(before.confidence)} → ${confidenceText(after.confidence)}`,
    );
  }
  if (before.responsible_system !== after.responsible_system) {
    found.push(
      `Sistema: ${systemLabel(before.responsible_system)} → ${systemLabel(after.responsible_system)}`,
    );
  }
  if (before.probable_cause !== after.probable_cause) found.push("Causa provável mudou");
  return found;
}
