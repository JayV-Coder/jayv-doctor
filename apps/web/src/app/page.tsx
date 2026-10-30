import Link from "next/link";
import { AuthShell, FormMessage } from "@/components/auth-shell";
import { OrgList, OrgSwitcher } from "@/components/org-switcher";
import { getMe } from "@/lib/api";
import { createClient } from "@/lib/supabase/server";

export default async function HomePage() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const me = await getMe();
  const organizations = me?.organizations ?? [];
  const active = organizations.find(({ id }) => id === me?.active_tenant_id);

  return (
    <AuthShell>
      <section className="stack">
        {me === null && <FormMessage error="Não foi possível carregar suas organizações." />}
        {active && <OrgSwitcher organizations={organizations} active={active} />}
        {me !== null && !active && organizations.length > 0 && (
          <OrgList organizations={organizations} activeId={null} />
        )}
        {me !== null && organizations.length === 0 && (
          <Link className="btn primary" href="/organizacoes/nova">
            Criar organização
          </Link>
        )}
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
