import type { ApiComponents } from "@aid/contracts";
import { apiFetch } from "@/lib/api";

type Schemas = ApiComponents["schemas"];
export type IncidentSummary = Schemas["IncidentSummary"];
export type IncidentPage = Schemas["IncidentPage"];
export type IncidentDetail = Schemas["IncidentDetail"];
export type IncidentSearch = Schemas["IncidentSearch"];
export type IncidentComment = Schemas["Comment"];

// Busca no corpo (POST): `q` pode ser um nº de pedido e não vai para URL nem log.
export async function searchIncidents(body: Partial<IncidentSearch>): Promise<IncidentPage | null> {
  const response = await apiFetch("/incidents/search", {
    method: "POST",
    body: JSON.stringify(body),
  }).catch(() => null);
  return response?.ok ? ((await response.json()) as IncidentPage) : null;
}

export async function getIncident(id: string): Promise<IncidentDetail | "not_found" | null> {
  const response = await apiFetch(`/incidents/${encodeURIComponent(id)}`).catch(() => null);
  if (response?.status === 404 || response?.status === 422) return "not_found";
  return response?.ok ? ((await response.json()) as IncidentDetail) : null;
}

export async function listComments(id: string): Promise<IncidentComment[] | null> {
  const response = await apiFetch(`/incidents/${encodeURIComponent(id)}/comments`).catch(
    () => null,
  );
  return response?.ok ? ((await response.json()) as IncidentComment[]) : null;
}
