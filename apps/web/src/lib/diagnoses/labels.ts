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

const VERDICTS: Record<string, { text: string; tone: ChipTone }> = {
  corrected: { text: "Corrigido", tone: "info" },
  accepted: { text: "Aceito", tone: "success" },
  rejected: { text: "Rejeitado", tone: "danger" },
};

// Veredito que vale para a versão: a correção pesa mais que o aceite, que pesa mais que a recusa.
export function verdictOf(feedback: readonly { verdict: string }[] = []): string | null {
  for (const verdict of ["corrected", "accepted", "rejected"]) {
    if (feedback.some((item) => item.verdict === verdict)) return verdict;
  }
  return null;
}

export function verdictLabel(verdict: string): string {
  return VERDICTS[verdict]?.text ?? verdict;
}

export function reviewable(status: string): boolean {
  return status === "published" || status === "inconclusive" || status === "failed_llm";
}

export function statusChip(diagnosis: {
  status: string;
  requires_human_review: boolean;
  feedback?: readonly { verdict: string }[];
}): {
  text: string;
  tone: ChipTone;
} {
  const verdict = verdictOf(diagnosis.feedback);
  const reviewed = verdict ? VERDICTS[verdict] : undefined;
  if (reviewed && reviewable(diagnosis.status)) return reviewed;
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

export function reviewTime(seconds: number | null): string {
  if (seconds === null) return "";
  if (seconds < 60) return "menos de 1 min após a publicação";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${String(minutes)} min após a publicação`;
  return `${String(Math.round(minutes / 60))} h após a publicação`;
}

// As notas do worker para "pedido híbrido, rodou só com as Regras" (Cota de IA esgotada ou envio
// ao LLM desligado) terminam assim; outras notas (por exemplo, sem Eventos) podem vir antes.
const WITHOUT_AI_SUFFIX = "Diagnóstico só com as Regras.";

export function withoutAiReason(diagnosis: {
  requested_mode: string;
  mode: string;
  status: string;
  verification_notes: string[];
}): string | null {
  if (diagnosis.requested_mode !== "hybrid" || diagnosis.mode !== "rules_only") return null;
  if (diagnosis.status === "failed_llm") return null;
  return diagnosis.verification_notes.find((note) => note.endsWith(WITHOUT_AI_SUFFIX)) ?? null;
}
