import Link from "next/link";
import { DashboardView } from "@/components/dashboard/dashboard-view";
import { PendingInvitationNotice } from "@/components/pending-invitation-notice";
import { EmptyState } from "@/components/ui/empty-state";
import { getMe, listIntegrations } from "@/lib/api";
import { getDashboard } from "@/lib/dashboard/api";
import { isManager } from "@/lib/orgs/labels";

const PERIODS = ["24h", "7d", "30d"];
const ENVIRONMENTS = ["prd", "hml", "dev"];

// Tela 4: Dashboard executivo. Período e Ambiente na URL (dá para compartilhar o recorte).
export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const period = PERIODS.includes(String(params.periodo)) ? String(params.periodo) : "24h";
  const environment = ENVIRONMENTS.includes(String(params.ambiente))
    ? String(params.ambiente)
    : null;
  const me = await getMe();
  // Só quem pode cadastrar recebe a sugestão; na dúvida (API fora), ela não aparece.
  const integrations = isManager(me?.active_role) ? await listIntegrations() : null;
  const suggest = integrations?.length === 0;
  const board = suggest ? null : await getDashboard({ period, environment });

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
      ) : board ? (
        <DashboardView board={board} period={period} environment={environment} />
      ) : (
        <EmptyState title="Nenhuma Execução recebida">
          O painel mostra Execuções, taxa de erro e Incidentes abertos assim que a primeira
          Integração enviar eventos.
        </EmptyState>
      )}
    </>
  );
}
