"use server";

import { revalidatePath } from "next/cache";
import { apiFetch, type WebhookSecret } from "@/lib/api";

const MESSAGES: Record<string, string> = {
  forbidden: "Seu papel não permite esta ação.",
  mfa_required: "Confirme a verificação em duas etapas para continuar.",
  name_taken: "Já existe um webhook com este nome.",
  not_found: "Webhook ou entrega não encontrada.",
  validation_error: "Confira os campos e tente de novo.",
};
const GENERIC = "Não foi possível concluir agora. Tente de novo.";
const OFFLINE = "Sem conexão. Tente de novo.";

export type Outcome<T = null> =
  { ok: true; value: T } | { ok: false; message: string; offline: boolean };

async function send<T>(path: string, init: RequestInit, key: string): Promise<Outcome<T>> {
  const response = await apiFetch(path, {
    ...init,
    headers: { "Idempotency-Key": key },
  }).catch(() => null);
  if (!response) return { ok: false, message: OFFLINE, offline: true };
  if (!response.ok) {
    const { code, title } = (await response.json().catch(() => ({}))) as {
      code?: string;
      title?: string;
    };
    // A API diz a regra do endereço (HTTPS, IP privado ou de metadados), sem ecoar a URL.
    const message = code === "unsafe_url" && title ? title : (MESSAGES[code ?? ""] ?? GENERIC);
    return { ok: false, message, offline: false };
  }
  revalidatePath("/webhooks");
  const value = response.status === 204 ? null : ((await response.json()) as T);
  return { ok: true, value: value as T };
}

export async function createWebhook(form: FormData, key: string): Promise<Outcome<WebhookSecret>> {
  return send<WebhookSecret>(
    "/webhooks",
    {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        url: form.get("url"),
        events: form.getAll("event").map(String),
      }),
    },
    key,
  );
}

export async function toggleWebhook(id: string, enabled: boolean, key: string): Promise<Outcome> {
  return send<null>(
    `/webhooks/${encodeURIComponent(id)}`,
    { method: "PATCH", body: JSON.stringify({ enabled }) },
    key,
  );
}

export async function rotateSecret(id: string, key: string): Promise<Outcome<WebhookSecret>> {
  return send<WebhookSecret>(
    `/webhooks/${encodeURIComponent(id)}/rotate-secret`,
    { method: "POST" },
    key,
  );
}

export async function deleteWebhook(id: string, key: string): Promise<Outcome> {
  return send<null>(`/webhooks/${encodeURIComponent(id)}`, { method: "DELETE" }, key);
}

export async function resendDelivery(id: string, key: string): Promise<Outcome> {
  return send<null>(
    `/webhook-deliveries/${encodeURIComponent(id)}/resend`,
    { method: "POST" },
    key,
  );
}
