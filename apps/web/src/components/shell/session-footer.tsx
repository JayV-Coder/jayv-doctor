import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { SignOut } from "./sign-out";

// Quem ainda não tem Organização também precisa sair ou cuidar da conta.
export async function SessionFooter() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();

  return (
    <section className="stack">
      <p className="small">
        Sessão ativa: <strong>{data?.claims.email}</strong>
      </p>
      <Link className="btn" href="/seguranca">
        Segurança da conta
      </Link>
      <SignOut />
    </section>
  );
}
