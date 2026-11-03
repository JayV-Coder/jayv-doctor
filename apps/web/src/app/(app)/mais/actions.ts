"use server";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";

const MESSAGES: Record<string, string> = {
  forbidden: "Seu papel não permite esta ação (exige MFA ativo).",
  mfa_required: "Confirme o MFA nesta sessão para continuar.",
  retention_out_of_bounds: "Retenção fora dos limites permitidos.",
  confirmation_mismatch: "Digite o identificador (slug) da Organização para confirmar.",
  hmac_unavailable: "A busca por Referência não está configurada.",
};
const GENERIC = "Não foi possível concluir agora. Tente de novo.";

async function send(path: string, init: RequestInit): Promise<string | null> {
  const response = await apiFetch(path, init).catch(() => null);
  if (!response) return "Sem conexão. Tente de novo.";
  if (!response.ok) {
    const { code } = (await response.json().catch(() => ({}))) as { code?: string };
    return MESSAGES[code ?? ""] ?? GENERIC;
  }
  revalidatePath("/mais");
  return null;
}

export async function setRetention(dataClass: string, days: number): Promise<string | null> {
  return send("/privacy/retention", {
    method: "PUT",
    body: JSON.stringify({ data_class: dataClass, days }),
  });
}

export async function setLlm(enabled: boolean): Promise<string | null> {
  return send("/privacy/llm", { method: "PUT", body: JSON.stringify({ enabled }) });
}

export async function requestDeletion(confirmation: string): Promise<string | null> {
  return send("/privacy/deletion", { method: "POST", body: JSON.stringify({ confirmation }) });
}

export async function cancelDeletion(): Promise<string | null> {
  return send("/privacy/deletion", { method: "DELETE" });
}

export type SubjectResult = { events: number; first_seen: string | null; last_seen: string | null };

// A Referência vai no corpo; a API calcula o HMAC e o número não chega ao banco nem aos logs.
export async function findSubject(
  reference: string,
): Promise<{ result: SubjectResult } | { error: string }> {
  const response = await apiFetch("/privacy/subject/search", {
    method: "POST",
    body: JSON.stringify({ reference }),
  }).catch(() => null);
  if (!response?.ok) {
    const { code } = (await response?.json().catch(() => ({}))) as { code?: string };
    return { error: MESSAGES[code ?? ""] ?? GENERIC };
  }
  return { result: (await response.json()) as SubjectResult };
}

export async function eraseSubject(
  reference: string,
): Promise<{ erased: number } | { error: string }> {
  const response = await apiFetch("/privacy/subject/erase", {
    method: "POST",
    body: JSON.stringify({ reference }),
  }).catch(() => null);
  if (!response?.ok) {
    const { code } = (await response?.json().catch(() => ({}))) as { code?: string };
    return { error: MESSAGES[code ?? ""] ?? GENERIC };
  }
  const { events_erased } = (await response.json()) as { events_erased: number };
  return { erased: events_erased };
}
