import type { ApiComponents } from "@aid/contracts";
import { apiFetch } from "@/lib/api";

type Schemas = ApiComponents["schemas"];
export type DiagnosisSummary = Schemas["DiagnosisSummary"];
export type DiagnosisDetail = Schemas["DiagnosisDetail"];

export async function listDiagnoses(incident: string): Promise<DiagnosisSummary[] | null> {
  const response = await apiFetch(`/incidents/${encodeURIComponent(incident)}/diagnoses`).catch(
    () => null,
  );
  return response?.ok ? ((await response.json()) as DiagnosisSummary[]) : null;
}

export async function getDiagnosis(id: string): Promise<DiagnosisDetail | null> {
  const response = await apiFetch(`/diagnoses/${encodeURIComponent(id)}`).catch(() => null);
  return response?.ok ? ((await response.json()) as DiagnosisDetail) : null;
}
