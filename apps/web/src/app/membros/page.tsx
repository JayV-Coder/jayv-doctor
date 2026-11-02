import Link from "next/link";
import { AuthShell, FormMessage } from "@/components/auth-shell";
import { MembersPanel } from "@/components/members-panel";
import { RenewSessionButton } from "@/components/renew-session-button";
import { apiFetch, getMe, type Invitation, type Member } from "@/lib/api";

export const metadata = { title: "Membros · Integration AI Doctor" };

async function load<T>(path: string): Promise<T | null> {
  const response = await apiFetch(path).catch(() => null);
  return response?.ok ? ((await response.json()) as T) : null;
}

export default async function MembersPage() {
  const [me, members, invitations] = await Promise.all([
    getMe(),
    load<Member[]>("/memberships"),
    load<Invitation[]>("/invitations"),
  ]);
  const role = me?.organizations.find(({ id }) => id === me.active_tenant_id)?.role;

  return (
    <AuthShell>
      <section className="stack">
        <h2 className="title">Membros</h2>
        {members && invitations && role ? (
          <MembersPanel members={members} invitations={invitations} viewerRole={role} />
        ) : (
          <>
            <FormMessage error="Só Owner e Admin, com a verificação em duas etapas, veem esta tela." />
            <RenewSessionButton />
          </>
        )}
        <Link className="btn" href="/">
          Voltar
        </Link>
      </section>
    </AuthShell>
  );
}
