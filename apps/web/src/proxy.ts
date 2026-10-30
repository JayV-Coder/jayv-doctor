import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { decideRedirect } from "@/lib/auth/gate";
import { toSessionState } from "@/lib/auth/session";
import { SUPABASE_KEY, SUPABASE_URL } from "@/lib/supabase/env";

// Roda em toda navegação: renova o JWT expirado e aplica o portão de sessão e MFA.
export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });
  const supabase = createServerClient(SUPABASE_URL, SUPABASE_KEY, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll(toSet) {
        for (const { name, value } of toSet) request.cookies.set(name, value);
        response = NextResponse.next({ request });
        for (const { name, value, options } of toSet) response.cookies.set(name, value, options);
      },
    },
  });

  const { data } = await supabase.auth.getClaims();
  const claims = data?.claims ?? null;
  // O nível vem da sessão no cookie: serve só para navegar. Quem barra de fato é o JWT, na API e no RLS.
  const levels = claims ? (await supabase.auth.mfa.getAuthenticatorAssuranceLevel()).data : null;

  const target = decideRedirect(request.nextUrl.pathname, toSessionState(claims, levels));
  if (target === null) return response;

  const url = request.nextUrl.clone();
  url.pathname = target;
  url.search = "";
  const redirect = NextResponse.redirect(url);
  for (const cookie of response.cookies.getAll()) redirect.cookies.set(cookie);
  return redirect;
}

export const config = {
  matcher: ["/((?!_next/|favicon.ico|.*\\.(?:svg|png|ico|webmanifest)$).*)"],
};
