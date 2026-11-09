import type { ApiComponents } from "@aid/contracts";
import { apiFetch } from "@/lib/api";

type Schemas = ApiComponents["schemas"];
export type ReportSummary = Schemas["ReportSummary"];
export type Report = Schemas["Report"];

export async function listReports(incident: string): Promise<ReportSummary[] | null> {
  const response = await apiFetch(`/incidents/${encodeURIComponent(incident)}/reports`).catch(
    () => null,
  );
  return response?.ok ? ((await response.json()) as ReportSummary[]) : null;
}

export async function getReport(id: string): Promise<Report | null> {
  const response = await apiFetch(`/reports/${encodeURIComponent(id)}`).catch(() => null);
  return response?.ok ? ((await response.json()) as Report) : null;
}
