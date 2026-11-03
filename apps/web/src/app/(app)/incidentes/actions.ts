"use server";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";
import { searchIncidents, type IncidentPage } from "@/lib/incidents/api";

const MESSAGES: Record<string, string> = {
  invalid_transition: "Essa mudança de status não é permitida.",
  invalid_assignee: "O responsável não é membro da Organização.",
  forbidden: "Seu papel não permite esta ação.",
  not_found: "Incidente não encontrado.",
  already_reviewed: "Você já revisou esta versão.",
  not_reviewable: "Esta versão ainda não pode ser revisada.",
  not_resolved: "Resolva o Incidente antes de promovê-lo.",
  not_reviewed: "Aceite ou corrija o Diagnóstico antes de promover.",
  already_promoted: "Este Incidente já está na Base de conhecimento.",
  idempotency_key_reused: "Esse pedido já foi enviado com outros dados. Feche e peça de novo.",
};
const GENERIC = "Não foi possível concluir agora. Tente de novo.";

async function send(
  path: string,
  init: RequestInit,
  refresh: string,
  invalid: string,
): Promise<string | null> {
  const response = await apiFetch(path, init).catch(() => null);
  if (!response) return "Sem conexão. Tente de novo.";
  if (!response.ok) {
    const { code } = (await response.json().catch(() => ({}))) as { code?: string };
    if (code === "validation_error") return invalid;
    return MESSAGES[code ?? ""] ?? GENERIC;
  }
  revalidatePath(refresh);
  return null;
}

export async function findIncidents(
  filters: { status: string[]; severity: string[] },
  q: string | null,
  cursor: string | null,
): Promise<IncidentPage | null> {
  return searchIncidents({
    status:
      filters.status.length > 0 ? (filters.status as IncidentPage["items"][0]["status"][]) : null,
    severity:
      filters.severity.length > 0
        ? (filters.severity as IncidentPage["items"][0]["severity"][])
        : null,
    q: q?.trim() || null,
    cursor,
  });
}

export async function changeIncident(
  id: string,
  change: {
    status?: string;
    severity?: string;
    assignee_id?: string | null;
    resolution_note?: string;
  },
): Promise<string | null> {
  return send(
    `/incidents/${encodeURIComponent(id)}`,
    { method: "PATCH", body: JSON.stringify(change) },
    `/incidentes/${id}`,
    "Confira a mudança: resolver exige a nota de resolução.",
  );
}

export async function addComment(
  id: string,
  body: string,
  mentions: string[],
): Promise<string | null> {
  return send(
    `/incidents/${encodeURIComponent(id)}/comments`,
    { method: "POST", body: JSON.stringify({ body_md: body, mentions }) },
    `/incidentes/${id}`,
    "O comentário precisa ter texto (até 4.000 caracteres).",
  );
}

// A chave nasce no navegador ao abrir o pedido: clique duplo ou repetição da rede devolvem o
// mesmo Diagnóstico.
export async function requestDiagnosis(
  id: string,
  body: { mode: "hybrid" | "rules_only"; include_knowledge_base: boolean },
  key: string,
): Promise<string | null> {
  return send(
    `/incidents/${encodeURIComponent(id)}/diagnoses`,
    { method: "POST", body: JSON.stringify(body), headers: { "Idempotency-Key": key } },
    `/incidentes/${id}`,
    "Confira o modo do Diagnóstico.",
  );
}

export async function reviewDiagnosis(
  incidentId: string,
  diagnosisId: string,
  body: {
    verdict: "accepted" | "corrected" | "rejected";
    correct_category?: string | undefined;
    correct_cause?: string | undefined;
    responsible_system?: string | undefined;
    comment?: string | undefined;
  },
): Promise<string | null> {
  return send(
    `/diagnoses/${encodeURIComponent(diagnosisId)}/feedback`,
    { method: "POST", body: JSON.stringify(body) },
    `/incidentes/${incidentId}`,
    "Corrigir exige a categoria (ex.: SAP_LOCK) ou a causa certa.",
  );
}

export async function promoteIncident(incidentId: string): Promise<string | null> {
  return send(
    `/incidents/${encodeURIComponent(incidentId)}/knowledge`,
    { method: "POST" },
    `/incidentes/${incidentId}`,
    "Não foi possível promover o Incidente.",
  );
}
