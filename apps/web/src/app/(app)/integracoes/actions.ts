"use server";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";

const MESSAGES: Record<string, string> = {
  integration_exists: "Já existe uma Integração com este nome neste Ambiente.",
  forbidden: "Seu papel não permite esta ação.",
  mfa_required: "Confirme a verificação em duas etapas para continuar.",
  not_found: "Integração não encontrada.",
  validation_error: "Confira os campos: nome de 2 a 80 caracteres, origem, destino e Ambiente.",
};
const GENERIC = "Não foi possível concluir agora. Tente de novo.";

// Devolvem a mensagem de erro, ou `null` quando deu certo.
async function change(path: string, init: RequestInit): Promise<string | null> {
  const response = await apiFetch(path, init).catch(() => null);
  if (!response) return GENERIC;
  revalidatePath("/integracoes");
  if (response.ok) return null;
  const { code } = (await response.json().catch(() => ({}))) as { code?: string };
  return MESSAGES[code ?? ""] ?? GENERIC;
}

// Campo opcional vazio vai como ausente: a API guarda `null`, não texto vazio.
function optional(form: FormData, field: string): string | undefined {
  const value = form.get(field);
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

export async function createIntegration(form: FormData): Promise<string | null> {
  return change("/integrations", {
    method: "POST",
    body: JSON.stringify({
      name: form.get("name"),
      source_system: form.get("source_system"),
      target_system: form.get("target_system"),
      environment: form.get("environment"),
      owner_team: optional(form, "owner_team"),
      description: optional(form, "description"),
    }),
  });
}

export async function archiveIntegration(id: string): Promise<string | null> {
  return change(`/integrations/${encodeURIComponent(id)}/archive`, { method: "POST" });
}
