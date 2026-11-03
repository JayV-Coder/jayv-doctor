import type { ApiComponents } from "@aid/contracts";
import { apiFetch } from "@/lib/api";

export type Dashboard = ApiComponents["schemas"]["Dashboard"];

export async function getDashboard(query: {
  period: string;
  environment: string | null;
}): Promise<Dashboard | null> {
  const params = new URLSearchParams({ period: query.period });
  if (query.environment) params.set("environment", query.environment);
  const response = await apiFetch(`/dashboard?${params.toString()}`).catch(() => null);
  return response?.ok ? ((await response.json()) as Dashboard) : null;
}
