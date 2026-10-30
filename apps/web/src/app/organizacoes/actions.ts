"use server";

import { apiFetch } from "@/lib/api";
import { createClient } from "@/lib/supabase/server";

const MESSAGES: Record<string, string> = {
  slug_taken: "Este identificador já está em uso. Escolha outro.",
  not_a_member: "Você não tem acesso a esta organização.",
};
const GENERIC = "Não foi possível concluir agora. Tente de novo.";

async function errorMessage(response: Response): Promise<string> {
  const { code } = (await response.json().catch(() => ({}))) as { code?: string };
  return MESSAGES[code ?? ""] ?? GENERIC;
}

// As ações devolvem a mensagem de erro, ou `null`: quem chama recarrega a página, para nada da
// Organização anterior ficar em memória e o proxy reaplicar o portão com o JWT novo.

// As claims mudam só na renovação: sem isto o JWT continuaria apontando para a Organização anterior.
async function renewSession(): Promise<void> {
  const supabase = await createClient();
  await supabase.auth.refreshSession();
}

export async function createOrganization(form: FormData): Promise<string | null> {
  const response = await apiFetch("/orgs", {
    method: "POST",
    body: JSON.stringify({
      name: form.get("name"),
      slug: form.get("slug"),
      segment: form.get("segment"),
      llm_provider: form.get("llm_provider"),
      dpa_accepted: form.get("dpa_accepted") === "on",
    }),
  }).catch(() => null);
  if (!response) return GENERIC;
  if (!response.ok) return errorMessage(response);
  await renewSession();
  return null;
}

export async function switchOrganization(tenantId: string): Promise<string | null> {
  const response = await apiFetch(`/orgs/${tenantId}/switch`, { method: "POST" }).catch(() => null);
  if (!response) return GENERIC;
  if (!response.ok) return errorMessage(response);
  await renewSession();
  return null;
}
