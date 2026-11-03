"use server";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";

const GENERIC = "Não foi possível concluir agora. Tente de novo.";
const MESSAGES: Record<string, string> = {
  forbidden: "Seu papel não permite esta ação.",
  invalid_filename: "Nome de arquivo inválido.",
  validation_error: "Use PDF, Markdown, TXT ou DOCX de até 20 MB.",
  not_found: "Documento não encontrado.",
};

async function message(response: Response | null): Promise<string> {
  if (!response) return "Sem conexão. Tente de novo.";
  const { code } = (await response.json().catch(() => ({}))) as { code?: string };
  return MESSAGES[code ?? ""] ?? GENERIC;
}

export async function createDocument(body: {
  title: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}): Promise<{ id: string; upload_url: string } | { error: string }> {
  const response = await apiFetch("/knowledge/documents", {
    method: "POST",
    body: JSON.stringify(body),
  }).catch(() => null);
  if (!response?.ok) return { error: await message(response) };
  return (await response.json()) as { id: string; upload_url: string };
}

export async function finishDocument(id: string): Promise<string | null> {
  const response = await apiFetch(`/knowledge/documents/${encodeURIComponent(id)}/finish`, {
    method: "POST",
  }).catch(() => null);
  if (!response?.ok) return message(response);
  revalidatePath("/conhecimento");
  return null;
}

export async function deleteDocument(id: string): Promise<string | null> {
  const response = await apiFetch(`/knowledge/documents/${encodeURIComponent(id)}`, {
    method: "DELETE",
  }).catch(() => null);
  if (!response?.ok) return message(response);
  revalidatePath("/conhecimento");
  return null;
}

export type Hit = {
  origin: "tenant" | "global";
  document_id: string;
  title: string;
  heading: string | null;
  excerpt: string;
};

// A pergunta vai no corpo, nunca na URL.
export async function searchKnowledge(
  q: string,
): Promise<{ items: Hit[]; mode: "hybrid" | "text" } | null> {
  const response = await apiFetch("/knowledge/search", {
    method: "POST",
    body: JSON.stringify({ q, k: 8 }),
  }).catch(() => null);
  return response?.ok
    ? ((await response.json()) as { items: Hit[]; mode: "hybrid" | "text" })
    : null;
}
