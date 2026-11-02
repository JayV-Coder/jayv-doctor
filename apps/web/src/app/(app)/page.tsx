import Link from "next/link";
import { PendingInvitationNotice } from "@/components/pending-invitation-notice";
import { EmptyState } from "@/components/ui/empty-state";
import { apiFetch, getMe, type Integration } from "@/lib/api";
import { isManager } from "@/lib/orgs/labels";

async function hasIntegrations(): Promise<boolean> {
  const response = await apiFetch("/integrations").catch(() => null);
  // Na dúvida, não sugere cadastro: a falha aparece na tela de Integrações.
  if (!response?.ok) return true;
  return ((await response.json()) as Integration[]).length > 0;
}

export default async function HomePage() {
  const [me, ready] = await Promise.all([getMe(), hasIntegrations()]);

  return (
    <>
      <PendingInvitationNotice />
      {!ready && isManager(me?.active_role) ? (
        // Fim do onboarding: Organização criada, falta o primeiro fluxo monitorado.
        <EmptyState
          title="Cadastre a primeira Integração"
          action={
            <Link className="btn primary" href="/integracoes">
              Cadastrar Integração
            </Link>
          }
        >
          A Integração é o fluxo de negócio monitorado, como Pedidos Salesforce → SAP. Execuções,
          Incidentes e Conectores se organizam por ela.
        </EmptyState>
      ) : (
        <EmptyState title="Nenhuma Execução recebida">
          O painel mostra Execuções, taxa de erro e Incidentes abertos assim que a primeira
          Integração enviar eventos.
        </EmptyState>
      )}
    </>
  );
}
