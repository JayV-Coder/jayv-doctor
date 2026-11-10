"use server";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";

const MESSAGES: Record<string, string> = {
  forbidden: "Seu papel não permite esta ação.",
  mfa_required: "Confirme a verificação em duas etapas para continuar.",
  name_taken: "Já existe um item com este nome.",
  not_found: "Regra, canal ou assinatura não encontrada.",
  validation_error: "Confira os campos e tente de novo.",
};
const GENERIC = "Não foi possível concluir agora. Tente de novo.";
const OFFLINE = "Sem conexão. Tente de novo.";

export type Outcome = { ok: true } | { ok: false; message: string; offline: boolean };

// A chave vem da tela: repetir sem resposta não duplica; com resposta, a tela gera outra.
async function send(path: string, init: RequestInit, key: string): Promise<Outcome> {
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
    // A API diz o campo e a regra (nunca o webhook, que nem volta).
    const message = code === "invalid_alert" && title ? title : (MESSAGES[code ?? ""] ?? GENERIC);
    return { ok: false, message, offline: false };
  }
  revalidatePath("/alertas");
  return { ok: true };
}

function text(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function quiet(form: FormData): object | null {
  const start = text(form, "quiet-start");
  const end = text(form, "quiet-end");
  return start && end ? { start, end, timezone: "America/Sao_Paulo" } : null;
}

function conditions(form: FormData): object {
  const type = text(form, "type");
  if (type === "incident") {
    return {
      type,
      min_severity: text(form, "severity") || "high",
      environments: form.getAll("environment").map(String),
    };
  }
  if (type === "error_rate") {
    return {
      type,
      threshold_pct: Number(text(form, "threshold") || "5"),
      minutes: Number(text(form, "minutes") || "10"),
    };
  }
  if (type === "diagnosis_review") return { type, minutes: Number(text(form, "minutes") || "30") };
  return { type };
}

export async function createRule(form: FormData, key: string): Promise<Outcome> {
  return send(
    "/alert-rules",
    {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        conditions: conditions(form),
        channels: form.getAll("channel").map(String),
        quiet_hours: quiet(form),
      }),
    },
    key,
  );
}

export async function toggleRule(id: string, enabled: boolean, key: string): Promise<Outcome> {
  return send(
    `/alert-rules/${encodeURIComponent(id)}`,
    { method: "PATCH", body: JSON.stringify({ enabled }) },
    key,
  );
}

export async function deleteRule(id: string, key: string): Promise<Outcome> {
  return send(`/alert-rules/${encodeURIComponent(id)}`, { method: "DELETE" }, key);
}

export async function createChannel(form: FormData, key: string): Promise<Outcome> {
  const type = text(form, "type");
  return send(
    "/notification-channels",
    {
      method: "POST",
      body: JSON.stringify({
        type,
        name: form.get("name"),
        ...(type === "slack" || type === "teams"
          ? { webhook_url: text(form, "webhook") }
          : { audience: text(form, "audience") || "managers" }),
      }),
    },
    key,
  );
}

export async function deleteChannel(id: string, key: string): Promise<Outcome> {
  return send(`/notification-channels/${encodeURIComponent(id)}`, { method: "DELETE" }, key);
}

export type DeviceSubscription = {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  user_agent: string;
};

export async function subscribePush(device: DeviceSubscription, key: string): Promise<Outcome> {
  return send("/push-subscriptions", { method: "POST", body: JSON.stringify(device) }, key);
}

export async function unsubscribePush(id: string, key: string): Promise<Outcome> {
  return send(`/push-subscriptions/${encodeURIComponent(id)}`, { method: "DELETE" }, key);
}

export async function saveQuiet(form: FormData, key: string): Promise<Outcome> {
  return send(
    "/alert-preferences",
    { method: "PUT", body: JSON.stringify({ quiet_hours: quiet(form) }) },
    key,
  );
}
