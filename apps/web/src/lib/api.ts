import type { ApiComponents } from "@aid/contracts";
import { cache } from "react";
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
type Me = Schemas["Me"];

// Só no servidor: o token sai do cookie da sessão e a API o valida.
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  return fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "content-type": "application/json",
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

// `cache`: o layout do shell e a página pedem o mesmo `/me` na mesma requisição.
export const getMe = cache(async (): Promise<Me | null> => {
  try {
    const response = await apiFetch("/me");
    return response.ok ? ((await response.json()) as Me) : null;
  } catch {
    return null;
  }
});
