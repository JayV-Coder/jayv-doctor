"use server";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";
import { getReport } from "@/lib/reports/api";

const GENERIC = "Não foi possível concluir agora. Tente de novo.";
const MESSAGES: Record<string, string> = {
  forbidden: "Seu papel não permite esta ação.",
  not_found: "Relatório não encontrado.",
  report_not_ready: "O relatório ainda não está pronto.",
};

type Result<T> = { ok: true; value: T } | { ok: false; error: string };

async function failure(response: Response | null): Promise<{ ok: false; error: string }> {
  if (!response) return { ok: false, error: "Sem conexão. Tente de novo." };
  const { code } = (await response.json().catch(() => ({}))) as { code?: string };
  return { ok: false, error: MESSAGES[code ?? ""] ?? GENERIC };
}

// A chave nasce no navegador: clique duplo ou repetição da rede devolvem o mesmo relatório.
export async function createReport(
  incident: string,
  body: { format: "pdf" | "md"; include_timeline: boolean; include_event_excerpts: boolean },
  key: string,
): Promise<Result<string>> {
  const response = await apiFetch(`/incidents/${encodeURIComponent(incident)}/reports`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Idempotency-Key": key },
  }).catch(() => null);
  if (!response?.ok) return failure(response);
  const { report_id } = (await response.json()) as { report_id: string };
  return { ok: true, value: report_id };
}

export async function reportStatus(id: string): Promise<string | null> {
  return (await getReport(id))?.status ?? null;
}

export async function shareReport(
  incident: string,
  report: string,
): Promise<Result<{ url: string; expires_at: string }>> {
  const response = await apiFetch(`/reports/${encodeURIComponent(report)}/shares`, {
    method: "POST",
  }).catch(() => null);
  if (!response?.ok) return failure(response);
  revalidatePath(`/incidentes/${incident}/relatorio`);
  const { url, expires_at } = (await response.json()) as { url: string; expires_at: string };
  return { ok: true, value: { url, expires_at } };
}

export async function revokeShare(
  incident: string,
  report: string,
  share: string,
): Promise<string | null> {
  const response = await apiFetch(
    `/reports/${encodeURIComponent(report)}/shares/${encodeURIComponent(share)}`,
    { method: "DELETE" },
  ).catch(() => null);
  if (!response?.ok) return (await failure(response)).error;
  revalidatePath(`/incidentes/${incident}/relatorio`);
  return null;
}
