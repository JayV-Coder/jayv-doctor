import Link from "next/link";
import { PendingInvitationNotice } from "@/components/pending-invitation-notice";
import { EmptyState } from "@/components/ui/empty-state";
import { getMe, listIntegrations } from "@/lib/api";
import { isManager } from "@/lib/orgs/labels";

export default async function HomePage() {
  const me = await getMe();
  // Só quem pode cadastrar recebe a sugestão; na dúvida (API fora), ela não aparece.
  const integrations = isManager(me?.active_role) ? await listIntegrations() : null;
  const suggest = integrations?.length === 0;

  return (
    <>
      <PendingInvitationNotice />
      {suggest ? (
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
