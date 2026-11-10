import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";

// Envio das Server Actions com `Idempotency-Key`: o resultado diz se deu certo, a mensagem em
// português e se faltou resposta (aí a tela repete com a mesma chave).

const MESSAGES: Record<string, string> = {
  forbidden: "Seu papel não permite esta ação.",
  mfa_required: "Confirme a verificação em duas etapas para continuar.",
  name_taken: "Já existe um item com este nome.",
  validation_error: "Confira os campos e tente de novo.",
};
const GENERIC = "Não foi possível concluir agora. Tente de novo.";
const OFFLINE = "Sem conexão. Tente de novo.";

export type Outcome<T = null> =
  { ok: true; value: T } | { ok: false; message: string; offline: boolean };

export async function send<T = null>(
  path: string,
  init: RequestInit,
  key: string,
  options: { page: string; messages?: Record<string, string>; detailed?: string[] },
): Promise<Outcome<T>> {
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
    // Erros de validação com o campo e a regra (nunca o valor): a API já diz em português.
    const message =
      code && title && options.detailed?.includes(code)
        ? title
        : (options.messages?.[code ?? ""] ?? MESSAGES[code ?? ""] ?? GENERIC);
    return { ok: false, message, offline: false };
  }
  revalidatePath(options.page);
  const value = response.status === 204 ? null : ((await response.json()) as T);
  return { ok: true, value: value as T };
}
