import type { ApiComponents } from "@aid/contracts";
import { apiFetch } from "@/lib/api";

export type PrivacySettings = ApiComponents["schemas"]["PrivacySettings"];

export async function getPrivacy(): Promise<PrivacySettings | null> {
  const response = await apiFetch("/privacy").catch(() => null);
  return response?.ok ? ((await response.json()) as PrivacySettings) : null;
}
