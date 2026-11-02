"use server";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";
import { createClient } from "@/lib/supabase/server";

const MESSAGES: Record<string, string> = {
  already_invited: "Já há um convite pendente para este e-mail.",
  already_member: "Esta pessoa já é membro da organização.",
  forbidden: "Seu papel não permite esta ação.",
  invitation_email_mismatch:
    "Este convite é de outro e-mail. Entre com o e-mail convidado, depois de confirmá-lo.",
  invitation_gone: "Este convite expirou ou já foi usado. Peça um novo.",
  last_owner: "A organização precisa de ao menos um Owner.",
  mail_unavailable: "O convite foi criado, mas o e-mail não saiu. Use Reenviar.",
  mfa_required: "Confirme a verificação em duas etapas para continuar.",
  not_found: "Convite ou membro não encontrado.",
};
const GENERIC = "Não foi possível concluir agora. Tente de novo.";

// Devolvem a mensagem de erro, ou `null` quando deu certo.
async function send(path: string, init: RequestInit): Promise<string | null> {
  const response = await apiFetch(path, init).catch(() => null);
  if (!response) return GENERIC;
  if (response.ok) return null;
  const { code } = (await response.json().catch(() => ({}))) as { code?: string };
  return MESSAGES[code ?? ""] ?? GENERIC;
}

async function change(path: string, init: RequestInit): Promise<string | null> {
  const failure = await send(path, init);
  revalidatePath("/membros");
  return failure;
}

export async function invite(email: string, role: string): Promise<string | null> {
  return change("/invitations", { method: "POST", body: JSON.stringify({ email, role }) });
}

export async function resendInvitation(id: string): Promise<string | null> {
  return change(`/invitations/${id}/resend`, { method: "POST" });
}

export async function revokeInvitation(id: string): Promise<string | null> {
  return change(`/invitations/${id}`, { method: "DELETE" });
}

export async function changeRole(id: string, role: string): Promise<string | null> {
  return change(`/memberships/${id}`, { method: "PATCH", body: JSON.stringify({ role }) });
}

export async function removeMember(id: string): Promise<string | null> {
  return change(`/memberships/${id}`, { method: "DELETE" });
}

// As claims mudam só na renovação: sem isto o JWT não traria a Organização do convite.
export async function acceptInvitation(
  token: string,
): Promise<{ accepted: boolean; error: string | null }> {
  const failure = await send("/invitations/accept", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
  if (failure) return { accepted: false, error: failure };
  const error = await renewSession();
  return { accepted: true, error };
}

export async function renewSession(): Promise<string | null> {
  const supabase = await createClient();
  const { error } = await supabase.auth.refreshSession();
  return error ? "Não renovamos sua sessão. Saia e entre de novo." : null;
}
