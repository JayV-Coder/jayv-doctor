import type { ApiComponents } from "@aid/contracts";
import { apiFetch } from "@/lib/api";

type Schemas = ApiComponents["schemas"];
export type AuditEntry = Schemas["AuditEntry"];
export type AuditPage = Schemas["AuditPage"];
export type AuditSearch = Schemas["AuditSearch"];

// Filtros no corpo (POST): o termo pode ser um e-mail e não vai para a URL nem para o log.
export async function searchAudit(
  body: Partial<AuditSearch>,
): Promise<AuditPage | "forbidden" | null> {
  const response = await apiFetch("/audit-logs/search", {
    method: "POST",
    body: JSON.stringify(body),
  }).catch(() => null);
  if (response?.status === 403) return "forbidden";
  return response?.ok ? ((await response.json()) as AuditPage) : null;
}
