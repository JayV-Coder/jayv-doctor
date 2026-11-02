import { redirect } from "next/navigation";
import { AuthShell, FormMessage } from "@/components/auth-shell";
import { OrgList } from "@/components/org-switcher";
import { PendingInvitationNotice } from "@/components/pending-invitation-notice";
import { SessionFooter } from "@/components/shell/session-footer";
import { getMe } from "@/lib/api";

export const metadata = { title: "Organizações · Integration AI Doctor" };

// Tela 3: quem tem Vínculo mas nenhuma Organização ativa escolhe aqui.
export default async function OrganizationsPage() {
  const me = await getMe();
  if (me?.organizations.length === 0) redirect("/organizacoes/nova");

  return (
    <AuthShell>
      <section className="stack">
        <PendingInvitationNotice />
        <h2 className="title">Escolha a organização</h2>
        {me === null ? (
          <FormMessage error="Não foi possível carregar suas organizações." />
        ) : (
          <OrgList organizations={me.organizations} activeId={me.active_tenant_id ?? null} />
        )}
      </section>
      <SessionFooter />
    </AuthShell>
  );
}
