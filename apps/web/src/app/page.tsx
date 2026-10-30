import Link from "next/link";
import { AuthShell } from "@/components/auth-shell";
import { createClient } from "@/lib/supabase/server";

export default async function HomePage() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  return (
    <AuthShell>
      <section className="stack">
        <p>
          Sessão ativa: <strong>{data?.claims.email}</strong>
        </p>
        <Link className="btn" href="/seguranca">
          Segurança da conta
        </Link>
        <form action="/auth/sair" method="post">
          <button className="btn" type="submit">
            Sair
          </button>
        </form>
      </section>
    </AuthShell>
  );
}
