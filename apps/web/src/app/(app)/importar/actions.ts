"use server";

import { revalidatePath } from "next/cache";
import { apiFetch, type CreatedImport } from "@/lib/api";

const MESSAGES: Record<string, string> = {
  forbidden: "Seu papel não permite importar logs.",
  not_found: "Integração não encontrada. Ela pode ter sido arquivada.",
  invalid_filename: "Nome de arquivo inválido.",
  import_not_pending: "Esta Importação já foi concluída ou recusada.",
  upload_missing: "O arquivo não chegou ao armazenamento. Tente enviar de novo.",
  storage_unavailable: "Armazenamento indisponível. Tente de novo em instantes.",
};
const GENERIC = "Não foi possível concluir agora. Tente de novo.";

async function failure(response: Response | null): Promise<string> {
  if (!response) return GENERIC;
  const { code } = (await response.json().catch(() => ({}))) as { code?: string };
  return MESSAGES[code ?? ""] ?? GENERIC;
}

export async function createImport(input: {
  integration_id: string;
  filename: string;
  size_bytes: number;
  sha256: string;
}): Promise<{ created: CreatedImport | null; error: string | null }> {
  const response = await apiFetch("/imports", {
    method: "POST",
    body: JSON.stringify(input),
  }).catch(() => null);
  if (!response?.ok) return { created: null, error: await failure(response) };
  revalidatePath("/importar");
  return { created: (await response.json()) as CreatedImport, error: null };
}

export async function completeImport(id: string): Promise<string | null> {
  const response = await apiFetch(`/imports/${encodeURIComponent(id)}/complete`, {
    method: "POST",
  }).catch(() => null);
  if (!response?.ok) return failure(response);
  revalidatePath("/importar");
  return null;
}
