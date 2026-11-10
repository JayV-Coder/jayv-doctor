"use server";

import type { WebhookSecret } from "@/lib/api";
import { send as post, type Outcome } from "@/lib/forms/send";

export type { Outcome };

const OPTIONS = {
  page: "/webhooks",
  messages: {
    not_found: "Webhook ou entrega não encontrada.",
    name_taken: "Já existe um webhook com este nome.",
  },
  detailed: ["unsafe_url"],
};

function send<T = null>(path: string, init: RequestInit, key: string): Promise<Outcome<T>> {
  return post<T>(path, init, key, OPTIONS);
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
  return send(
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
  return send(`/webhooks/${encodeURIComponent(id)}`, { method: "DELETE" }, key);
}

export async function resendDelivery(id: string, key: string): Promise<Outcome> {
  return send(`/webhook-deliveries/${encodeURIComponent(id)}/resend`, { method: "POST" }, key);
}
