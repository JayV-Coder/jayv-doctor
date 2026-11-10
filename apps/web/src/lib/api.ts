import { headers } from "next/headers";
import type { ApiComponents } from "@aid/contracts";
import { cache } from "react";
import { toQuiet, type Quiet } from "@/lib/alerts/labels";
import { createClient } from "@/lib/supabase/server";

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

// Gerados do OpenAPI da API (`make contracts`): o contrato vem de lá, não daqui.
type Schemas = ApiComponents["schemas"];
export type Organization = Schemas["Organization"];
export type Member = Schemas["Member"];
export type Invitation = Schemas["Invitation"];
export type Integration = Schemas["Integration"];
export type Import = Schemas["Import"];
export type CreatedImport = Schemas["CreatedImport"];
export type ExecutionSummary = Schemas["ExecutionSummary"];
export type ExecutionPage = Schemas["ExecutionPage"];
export type ExecutionDetail = Schemas["ExecutionDetail"];
export type EventDetail = Schemas["EventDetail"];
export type ExecutionSearch = Schemas["ExecutionSearch"];
export type Connector = Schemas["Connector"];
export type AlertRule = Schemas["AlertRule"];
export type NotificationChannel = Schemas["Channel"];
export type PushSubscriptionInfo = Schemas["PushSubscription"];
export type Webhook = Schemas["Webhook"];
export type WebhookSecret = Schemas["WebhookSecret"];
export type WebhookDelivery = Schemas["Delivery"];
export type CorrelationMapping = Schemas["CorrelationMapping"];
export type Agent = Schemas["Agent"];
export type RegistrationToken = Schemas["RegistrationToken"];
export type ConnectorSync = Schemas["ConnectorSync"];
type Me = Schemas["Me"];

// Só no servidor: o token sai do cookie da sessão e a API o valida.
// Para a Trilha de auditoria: o IP do navegador (último salto, posto pelo balanceador do Cloud
// Run) e o user agent dele seguem para a API, que confia em AID_TRUSTED_PROXY_HOPS saltos.
async function clientHeaders(): Promise<Record<string, string>> {
  try {
    const incoming = await headers();
    const hops = (incoming.get("x-forwarded-for") ?? "")
      .split(",")
      .map((hop) => hop.trim())
      .filter(Boolean);
    const agent = incoming.get("user-agent");
    return {
      ...(hops.length > 0 && { "x-forwarded-for": hops[hops.length - 1] ?? "" }),
      ...(agent && { "user-agent": agent }),
    };
  } catch {
    // Fora de uma requisição (build, script): não há navegador a descrever.
    return {};
  }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  return fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    cache: "no-store",
    // Headers de quem chama (ex.: Idempotency-Key) entram; a autorização é sempre a da sessão.
    headers: {
      "content-type": "application/json",
      ...(await clientHeaders()),
      ...Object.fromEntries(new Headers(init.headers)),
      authorization: `Bearer ${data.session?.access_token ?? ""}`,
    },
  });
}

// Integrações da Organização ativa, sem as arquivadas; `null` se a API não respondeu.
export async function listIntegrations(): Promise<Integration[] | null> {
  const response = await apiFetch("/integrations").catch(() => null);
  return response?.ok ? ((await response.json()) as Integration[]) : null;
}

// Últimas Importações da Organização ativa; `null` se a API não respondeu.
export async function listImports(): Promise<Import[] | null> {
  const response = await apiFetch("/imports").catch(() => null);
  return response?.ok ? ((await response.json()) as Import[]) : null;
}

// Busca no corpo (POST): o termo pode ser um número de pedido e não vai para URL nem log.
export async function searchExecutions(
  body: Partial<ExecutionSearch>,
): Promise<ExecutionPage | null> {
  const response = await apiFetch("/executions/search", {
    method: "POST",
    body: JSON.stringify(body),
  }).catch(() => null);
  return response?.ok ? ((await response.json()) as ExecutionPage) : null;
}

// `"not_found"` quando não existe nesta Organização; `null` se a API não respondeu.
async function getOne<T>(path: string): Promise<T | "not_found" | null> {
  const response = await apiFetch(path).catch(() => null);
  if (response?.status === 404 || response?.status === 422) return "not_found";
  return response?.ok ? ((await response.json()) as T) : null;
}

async function getList<T>(path: string): Promise<T | null> {
  const response = await apiFetch(path).catch(() => null);
  return response?.ok ? ((await response.json()) as T) : null;
}

// Webhooks de saída (#42), só para gestores; `null` se a API não respondeu ou recusou.
export async function listWebhooks(): Promise<Webhook[] | null> {
  return getList<Webhook[]>("/webhooks");
}

export async function listWebhookDeliveries(id: string): Promise<WebhookDelivery[] | null> {
  return getList<WebhookDelivery[]>(`/webhooks/${encodeURIComponent(id)}/deliveries`);
}

// Tela 20 (#41): Regras, canais, push e silêncio; `null` se a API não respondeu.
export async function getAlerts(): Promise<{
  rules: AlertRule[];
  channels: NotificationChannel[];
  subscriptions: PushSubscriptionInfo[];
  quiet: Quiet;
  pushKey: string | null;
} | null> {
  const [rules, channels, subscriptions, preferences, key] = await Promise.all([
    getList<AlertRule[]>("/alert-rules"),
    getList<NotificationChannel[]>("/notification-channels"),
    getList<PushSubscriptionInfo[]>("/push-subscriptions"),
    getList<Schemas["Preferences"]>("/alert-preferences"),
    getList<Schemas["PushKey"]>("/push/key"),
  ]);
  if (!rules || !channels || !subscriptions || !preferences) return null;
  return {
    rules,
    channels,
    subscriptions,
    quiet: toQuiet(preferences.quiet_hours),
    pushKey: key?.public_key ?? null,
  };
}

// Mapas de identificadores da Integração (#40).
export async function listMappings(
  integration: string,
): Promise<CorrelationMapping[] | "not_found" | null> {
  return getOne<CorrelationMapping[]>(
    `/integrations/${encodeURIComponent(integration)}/correlation-mappings`,
  );
}

export async function getExecution(id: string): Promise<ExecutionDetail | "not_found" | null> {
  return getOne<ExecutionDetail>(`/executions/${encodeURIComponent(id)}`);
}

export async function getEvent(
  id: string,
  at: string | null = null,
): Promise<EventDetail | "not_found" | null> {
  const query = at ? `?at=${encodeURIComponent(at)}` : "";
  return getOne<EventDetail>(`/events/${encodeURIComponent(id)}${query}`);
}

// Conectores da Organização ativa; `null` se a API não respondeu.
export async function listConnectors(): Promise<Connector[] | null> {
  const response = await apiFetch("/connectors").catch(() => null);
  return response?.ok ? ((await response.json()) as Connector[]) : null;
}

// Agentes locais da Organização ativa (#39); `null` se a API não respondeu.
export async function listAgents(): Promise<Agent[] | null> {
  const response = await apiFetch("/agents").catch(() => null);
  return response?.ok ? ((await response.json()) as Agent[]) : null;
}

export async function getConnector(id: string): Promise<Connector | "not_found" | null> {
  return getOne<Connector>(`/connectors/${encodeURIComponent(id)}`);
}

// As 50 Sincronizações mais recentes de um Conector; `null` se a API não respondeu.
export async function listConnectorSyncs(id: string): Promise<ConnectorSync[] | null> {
  const response = await apiFetch(`/connectors/${encodeURIComponent(id)}/syncs`).catch(() => null);
  return response?.ok ? ((await response.json()) as ConnectorSync[]) : null;
}

// `cache`: o layout do shell e a página pedem o mesmo `/me` na mesma requisição.
export const getMe = cache(async (): Promise<Me | null> => {
  try {
    const response = await apiFetch("/me");
    return response.ok ? ((await response.json()) as Me) : null;
  } catch {
    return null;
  }
});
