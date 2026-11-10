import Link from "next/link";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getMe, listIntegrations } from "@/lib/api";
import { canManage } from "@/lib/orgs/labels";
import { GcpWizard } from "./gcp-wizard";
import { SalesforceWizard } from "./salesforce-wizard";

export const metadata = { title: "Novo conector · Integration AI Doctor" };

// Tela 12: assistente do Conector em 4 passos, do Google Cloud (padrão) ou do Salesforce (#37).
export default async function NewConnectorPage({
  searchParams,
}: {
  searchParams: Promise<{ provedor?: string | string[] }>;
}) {
  const [{ provedor }, me, integrations] = await Promise.all([
    searchParams,
    getMe(),
    listIntegrations(),
  ]);
  const salesforce = provedor === "salesforce";
  if (!canManage(me)) {
    return (
      <EmptyState
        title="Só Owner ou Admin configuram Conectores"
        action={
          <Link className="btn" href="/conectores">
            Voltar aos Conectores
          </Link>
        }
      >
        Configurar a coleta exige o papel de Owner ou Admin, com verificação em duas etapas.
      </EmptyState>
    );
  }
  if (integrations === null) {
    return (
      <ErrorState title="Não foi possível carregar as Integrações" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  if (integrations.length === 0) {
    return (
      <EmptyState
        title="Cadastre uma Integração antes"
        action={
          <Link className="btn" href="/integracoes">
            Ir para Integrações
          </Link>
        }
      >
        Os logs coletados pelo Conector pertencem a uma Integração.
      </EmptyState>
    );
  }
  const options = integrations.map(({ id, name, environment }) => ({ id, name, environment }));
  return (
    <>
      <nav className="row" aria-label="Provedor">
        <Link
          className={salesforce ? "btn" : "btn primary"}
          href="/conectores/novo"
          aria-current={salesforce ? undefined : "page"}
        >
          Google Cloud
        </Link>
        <Link
          className={salesforce ? "btn primary" : "btn"}
          href="/conectores/novo?provedor=salesforce"
          aria-current={salesforce ? "page" : undefined}
        >
          Salesforce
        </Link>
      </nav>
      {salesforce ? (
        <SalesforceWizard integrations={options} />
      ) : (
        <GcpWizard tenantId={me?.active_tenant_id ?? ""} integrations={options} />
      )}
    </>
  );
}
