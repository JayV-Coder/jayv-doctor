import { NextResponse, type NextRequest } from "next/server";
import { safeNext } from "@/lib/auth/gate";
import { SITE_URL } from "@/lib/supabase/env";
import { createClient } from "@/lib/supabase/server";

const EMAIL_TYPES: readonly string[] = ["magiclink", "recovery", "invite", "email"];

// `token_hash` vem dos e-mails e funciona em outro navegador (app de e-mail no celular);
// `code` vem do Google, cujo fluxo PKCE começa e termina no mesmo navegador.
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const code = params.get("code");
  const tokenHash = params.get("token_hash");
  const type = params.get("type");
  const supabase = await createClient();

  let failed = true;
  if (code) {
    failed = (await supabase.auth.exchangeCodeForSession(code)).error !== null;
  } else if (tokenHash && type && EMAIL_TYPES.includes(type)) {
    const result = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type,
    });
    failed = result.error !== null;
  }

  const target = failed ? "/login?erro=link" : safeNext(params.get("next"));
  return NextResponse.redirect(new URL(target, SITE_URL), 303);
}
