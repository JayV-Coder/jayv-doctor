import { PendingInvitationNotice } from "@/components/pending-invitation-notice";
import { EmptyState } from "@/components/ui/empty-state";

export default function HomePage() {
  return (
    <>
      <PendingInvitationNotice />
      <EmptyState title="Nenhuma Execução recebida">
        O painel mostra Execuções, taxa de erro e Incidentes abertos assim que a primeira Integração
        enviar eventos.
      </EmptyState>
    </>
  );
}
