"use server";

import type { ApiComponents } from "@aid/contracts";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";

const MESSAGES: Record<string, string> = {
  connector_paused: "Retome o Conector antes de sincronizar.",
  connector_disabled: "Este Conector foi desativado pela plataforma.",
  sync_running: "Já há uma Sincronização em andamento.",
  provider_unavailable: "Este provedor ainda não tem Conector.",
  forbidden: "Seu papel não permite esta ação.",
  mfa_required: "Confirme a verificação em duas etapas para continuar.",
  not_found: "Conector ou Integração não encontrado.",
  validation_error: "Confira os campos e tente de novo.",
};
const GENERIC = "Não foi possível concluir agora. Tente de novo.";
const OFFLINE = "Sem conexão. Tente de novo.";

// Gerado do OpenAPI: `capabilities` são as fontes da conta do cliente (Salesforce, #37).
export type TestOutcome = ApiComponents["schemas"]["TestResult"];

async function failure(response: Response): Promise<string> {
  const { code, title } = (await response.json().catch(() => ({}))) as {
    code?: string;
    title?: string;
  };
  // A API diz qual campo e qual regra, nunca o valor (docs/api/connectors.md).
  if (code === "invalid_config" && title) return title;
  return MESSAGES[code ?? ""] ?? GENERIC;
}

// Devolvem a mensagem de erro, ou `null` quando deu certo.
// `refresh: false` quando a tela não muda na hora (o pedido de Sincronização só entra na fila).
async function change(path: string, init: RequestInit, refresh = true): Promise<string | null> {
  const response = await apiFetch(path, init).catch(() => null);
  if (!response) return OFFLINE;
  if (!response.ok) return failure(response);
  if (refresh) revalidatePath("/conectores", "layout");
  return null;
}

async function test(path: string, body: object): Promise<TestOutcome> {
  const response = await apiFetch(path, { method: "POST", body: JSON.stringify(body) }).catch(
    () => null,
  );
  if (!response) return { ok: false, message: OFFLINE };
  if (!response.ok) return { ok: false, message: await failure(response) };
  return (await response.json()) as TestOutcome;
}

function connectorPath(id: string, suffix = ""): string {
  return `/connectors/${encodeURIComponent(id)}${suffix}`;
}

export async function runConnectorAction(
  id: string,
  action: "sync" | "pause" | "resume",
): Promise<string | null> {
  return change(connectorPath(id, `/${action}`), { method: "POST" }, action !== "sync");
}

// A credencial salva não sai do Vault: o teste de um Conector salvo usa a enviada aqui, que é
// descartada depois do teste.
export async function testSavedConnection(id: string, credential: string): Promise<TestOutcome> {
  return test(connectorPath(id, "/test"), { credential });
}

export async function replaceCredential(id: string, credential: string): Promise<string | null> {
  return change(connectorPath(id), { method: "PATCH", body: JSON.stringify({ credential }) });
}

export async function editConnector(id: string, form: FormData): Promise<string | null> {
  return change(connectorPath(id), {
    method: "PATCH",
    body: JSON.stringify({
      name: form.get("name"),
      sync_interval_seconds: Number(form.get("sync_interval_seconds")),
    }),
  });
}

// Assistente: testa provedor, config e credencial antes de salvar; a API não grava nada.
export async function testNewConnection(
  config: Record<string, unknown>,
  credential: string,
  provider: "gcp" | "salesforce" = "gcp",
): Promise<TestOutcome> {
  return test("/connectors/test", { provider, config, credential });
}

export async function createConnector(request: {
  integration_id: string;
  name: string;
  config: Record<string, unknown>;
  sync_interval_seconds: number;
  credential: string;
  provider?: "gcp" | "salesforce";
}): Promise<{ id: string } | { error: string }> {
  const response = await apiFetch("/connectors", {
    method: "POST",
    body: JSON.stringify({ provider: "gcp", ...request }),
  }).catch(() => null);
  if (!response) return { error: OFFLINE };
  if (!response.ok) return { error: await failure(response) };
  revalidatePath("/conectores", "layout");
  const { id } = (await response.json()) as { id: string };
  return { id };
}
