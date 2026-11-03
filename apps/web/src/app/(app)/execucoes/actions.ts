"use server";

import { apiFetch, searchExecutions, type ExecutionPage } from "@/lib/api";
import { toSearch, type Filters } from "@/lib/executions/filters";

// O termo vem no corpo da Server Action e segue no corpo para a API: nunca fica numa URL.
export async function findExecutions(
  filters: Filters,
  since: string,
  q: string | null,
  cursor: string | null,
): Promise<ExecutionPage | null> {
  return searchExecutions({
    ...toSearch(filters, new Date(since)),
    q: q?.trim() || null,
    cursor,
  });
}

// URL assinada de 5 min; `null` sem permissão ou com o Log já vencido.
export async function rawLogUrl(id: string): Promise<string | null> {
  const response = await apiFetch(`/raw-logs/${encodeURIComponent(id)}/download`).catch(() => null);
  if (!response?.ok) return null;
  const { url } = (await response.json()) as { url: string };
  return url;
}
