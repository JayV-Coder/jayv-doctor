"use server";

import { send as post, type Outcome } from "@/lib/forms/send";

export type { Outcome };

const OPTIONS = {
  page: "/alertas",
  messages: { not_found: "Regra, canal ou assinatura não encontrada." },
  detailed: ["invalid_alert"],
};

function send(path: string, init: RequestInit, key: string): Promise<Outcome> {
  return post(path, init, key, OPTIONS);
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
