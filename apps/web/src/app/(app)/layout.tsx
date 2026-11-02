import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { AuthShell } from "@/components/auth-shell";
import { NavBar } from "@/components/shell/nav-bar";
import { SessionFooter } from "@/components/shell/session-footer";
import { TopBar } from "@/components/shell/top-bar";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getMe } from "@/lib/api";

// O proxy cuida de sessão e MFA; aqui entra o que só a API sabe: há Organização, e qual está ativa.
export default async function AppLayout({ children }: { children: ReactNode }) {
  const me = await getMe();
  if (me === null) {
    return (
      <AuthShell>
        <ErrorState title="Não foi possível carregar suas organizações" action={<ReloadButton />}>
          O serviço não respondeu. Seus dados continuam seguros.
        </ErrorState>
        <SessionFooter />
      </AuthShell>
    );
  }
  if (me.organizations.length === 0) redirect("/organizacoes/nova");
  const active = me.organizations.find(({ id }) => id === me.active_tenant_id);
  if (!active) redirect("/organizacoes");

  return (
    <div className="app">
      <NavBar />
      <div className="app-main">
        <TopBar organizations={me.organizations} active={active} />
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
