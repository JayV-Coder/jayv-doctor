"use server";

import { searchAudit, type AuditPage, type AuditSearch } from "@/lib/audit/api";

export async function findAudit(
  category: string | null,
  q: string | null,
  cursor: string | null,
): Promise<AuditPage | null> {
  const page = await searchAudit({
    ...(category ? { category: category as NonNullable<AuditSearch["category"]> } : {}),
    ...(q ? { q } : {}),
    ...(cursor ? { cursor } : {}),
  });
  return page === "forbidden" ? null : page;
}
