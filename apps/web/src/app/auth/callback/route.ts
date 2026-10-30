import { NextResponse, type NextRequest } from "next/server";
import { safeNext } from "@/lib/auth/gate";
import { SITE_URL } from "@/lib/supabase/env";
import { createClient } from "@/lib/supabase/server";

const EMAIL_TYPES = ["magiclink", "recovery", "invite", "email"] as const;
type EmailType = (typeof EMAIL_TYPES)[number];

function isEmailType(value: unknown): value is EmailType {
  return EMAIL_TYPES.includes(value as EmailType);
}

function redirectTo(path: string) {
  return NextResponse.redirect(new URL(path, SITE_URL), 303);
}

// `code` vem do Google, cujo fluxo PKCE começa e termina no mesmo navegador.
export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const supabase = await createClient();
  if (!code || (await supabase.auth.exchangeCodeForSession(code)).error) {
    return redirectTo("/login?erro=link");
  }
  return redirectTo(safeNext(request.nextUrl.searchParams.get("next")));
}

// Links de e-mail: `token_hash` funciona em outro navegador (app de e-mail no celular). Só o POST
// da tela /auth/confirmar gasta o token, porque scanners de e-mail corporativo abrem o link com
// GET. A origem é conferida para ninguém logar a vítima na própria conta com um formulário externo.
export async function POST(request: NextRequest) {
  if (request.headers.get("origin") !== new URL(SITE_URL).origin) {
    return redirectTo("/login?erro=link");
  }
  const form = await request.formData();
  const tokenHash = form.get("token_hash");
  const type = form.get("type");
  if (typeof tokenHash !== "string" || !isEmailType(type)) return redirectTo("/login?erro=link");

  const supabase = await createClient();
  const { error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
  if (error) return redirectTo("/login?erro=link");
  const next = form.get("next");
  return redirectTo(safeNext(typeof next === "string" ? next : null));
}
