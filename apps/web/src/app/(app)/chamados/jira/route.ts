import { NextResponse, type NextRequest } from "next/server";
import { apiFetch } from "@/lib/api";
import { SITE_URL } from "@/lib/supabase/env";

// Volta do consentimento do Atlassian (#43): o código e o `state` vão à API, com a sessão de
// quem pediu; o `state` é de uso único e desta Organização.
export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  let result = "erro";
  if (code && state) {
    const response = await apiFetch("/itsm/jira/callback", {
      method: "POST",
      body: JSON.stringify({ code, state }),
    }).catch(() => null);
    result = response?.ok ? "conectado" : "erro";
  }
  return NextResponse.redirect(new URL(`/chamados?jira=${result}`, SITE_URL), 303);
}
