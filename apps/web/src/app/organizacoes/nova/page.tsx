import { AuthShell } from "@/components/auth-shell";
import { PendingInvitationNotice } from "@/components/pending-invitation-notice";
import { SessionFooter } from "@/components/shell/session-footer";
import { getMe } from "@/lib/api";
import { NewOrganizationForm } from "./new-organization-form";

export const metadata = { title: "Criar organização · Integration AI Doctor" };

// Onboarding: o shell manda para cá quem ainda não tem Organização.
export default async function NewOrganizationPage() {
  const me = await getMe();

  return (
    <AuthShell>
      <PendingInvitationNotice />
      <NewOrganizationForm canGoBack={(me?.organizations.length ?? 0) > 0} />
      <SessionFooter />
    </AuthShell>
  );
}
