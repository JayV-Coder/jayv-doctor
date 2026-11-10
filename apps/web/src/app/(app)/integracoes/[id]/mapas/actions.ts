"use server";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";
import { keysFromForm, lookupFromForm } from "@/lib/correlation/form";

const MESSAGES: Record<string, string> = {
  forbidden: "Seu papel não permite esta ação.",
  mfa_required: "Confirme a verificação em duas etapas para continuar.",
  mapping_exists: "Já existe um Mapa com este nome nesta Integração.",
  not_found: "Integração ou Mapa não encontrado.",
  validation_error: "Confira os campos e tente de novo.",
};
const GENERIC = "Não foi possível concluir agora. Tente de novo.";
const OFFLINE = "Sem conexão. Tente de novo.";

export type Outcome = { ok: true } | { ok: false; message: string; offline: boolean };

async function send(path: string, init: RequestInit, key: string, page: string): Promise<Outcome> {
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
    // A API diz qual item e qual regra do Mapa falhou, nunca um valor de Evento.
    const message = code === "invalid_mapping" && title ? title : (MESSAGES[code ?? ""] ?? GENERIC);
    return { ok: false, message, offline: false };
  }
  revalidatePath(page);
  return { ok: true };
}

export async function createMapping(
  integration: string,
  form: FormData,
  key: string,
): Promise<Outcome> {
  const window = Number(form.get("window") ?? "60");
  return send(
    `/integrations/${encodeURIComponent(integration)}/correlation-mappings`,
    {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        keys: keysFromForm(form),
        window_minutes: Number.isFinite(window) ? window : 60,
        reconcile: form.get("reconcile") === "on",
        lookup: lookupFromForm(form),
      }),
    },
    key,
    `/integracoes/${integration}/mapas`,
  );
}

export async function deleteMapping(
  integration: string,
  id: string,
  key: string,
): Promise<Outcome> {
  return send(
    `/correlation-mappings/${encodeURIComponent(id)}`,
    { method: "DELETE" },
    key,
    `/integracoes/${integration}/mapas`,
  );
}
