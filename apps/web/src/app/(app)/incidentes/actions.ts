"use server";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";
import { searchIncidents, type IncidentPage } from "@/lib/incidents/api";

const MESSAGES: Record<string, string> = {
  invalid_transition: "Essa mudança de status não é permitida.",
  invalid_assignee: "O responsável não é membro da Organização.",
  forbidden: "Seu papel não permite esta ação.",
  not_found: "Incidente não encontrado.",
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
