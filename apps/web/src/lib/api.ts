import { createClient } from "@/lib/supabase/server";

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

export interface Organization {
  id: string;
  name: string;
  slug: string;
  role: string;
}

interface Me {
  organizations: Organization[];
  active_tenant_id: string | null;
}

// Só no servidor: o token sai do cookie da sessão e a API o valida.
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  return fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${data.session?.access_token ?? ""}`,
    },
  });
}

export async function getMe(): Promise<Me | null> {
  try {
    const response = await apiFetch("/me");
    return response.ok ? ((await response.json()) as Me) : null;
  } catch {
    return null;
  }
}
