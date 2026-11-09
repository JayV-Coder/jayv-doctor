"use server";

import { revalidatePath } from "next/cache";
import { apiFetch, type RegistrationToken } from "@/lib/api";

const MESSAGES: Record<string, string> = {
  forbidden: "Seu papel não permite esta ação.",
  mfa_required: "Confirme a verificação em duas etapas para continuar.",
  not_found: "Agente ou Integração não encontrado.",
  validation_error: "Confira os campos e tente de novo.",
};
const GENERIC = "Não foi possível concluir agora. Tente de novo.";
const OFFLINE = "Sem conexão. Tente de novo.";

export type Issued = { ok: true; token: RegistrationToken } | { ok: false; message: string };

async function failure(response: Response): Promise<string> {
  const { code, title } = (await response.json().catch(() => ({}))) as {
    code?: string;
    title?: string;
  };
  // A API diz qual coleta e qual regra da allowlist falhou (docs/api/agents.md).
  if (code === "invalid_config" && title) return title;
  return MESSAGES[code ?? ""] ?? GENERIC;
}

async function issue(path: string, init: RequestInit): Promise<Issued> {
  const response = await apiFetch(path, init).catch(() => null);
  if (!response) return { ok: false, message: OFFLINE };
  if (!response.ok) return { ok: false, message: await failure(response) };
  revalidatePath("/conectores/agentes");
  return { ok: true, token: (await response.json()) as RegistrationToken };
}

function text(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function collections(form: FormData): object[] {
  const found: object[] = [];
  const folder = text(form, "directory");
  if (folder) {
    found.push({ type: "directory", path: folder, pattern: text(form, "pattern") || "*.csv" });
  }
  if (form.get("idoc") === "on") found.push({ type: "rfc_table", table: "EDIDS" });
  const custom = text(form, "function");
  if (custom) found.push({ type: "rfc_function", name: custom });
  return found;
}

export async function createAgent(form: FormData): Promise<Issued> {
  return issue("/agents", {
    method: "POST",
    body: JSON.stringify({
      name: form.get("name"),
      integration_id: form.get("integration_id"),
      config: { collections: collections(form) },
    }),
  });
}

// Rotação: o segredo e a chave atuais param na hora; o agente se registra de novo com o token.
export async function rotateAgent(id: string): Promise<Issued> {
  return issue(`/agents/${encodeURIComponent(id)}/rotate`, { method: "POST" });
}

export async function revokeAgent(id: string): Promise<string | null> {
  const response = await apiFetch(`/agents/${encodeURIComponent(id)}/revoke`, {
    method: "POST",
  }).catch(() => null);
  if (!response) return OFFLINE;
  if (!response.ok) return failure(response);
  revalidatePath("/conectores/agentes");
  return null;
}
