import Link from "next/link";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getMe, listIntegrations } from "@/lib/api";
import { isManager } from "@/lib/orgs/labels";
import { GcpWizard } from "./gcp-wizard";

export const metadata = { title: "Conector GCP · Integration AI Doctor" };

// Tela 12: assistente do Conector do Google Cloud em 4 passos.
export default async function NewConnectorPage() {
  const [me, integrations] = await Promise.all([getMe(), listIntegrations()]);
  if (!isManager(me?.active_role) || me?.aal !== "aal2") {
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
  return (
    <GcpWizard
      integrations={integrations.map(({ id, name, environment }) => ({ id, name, environment }))}
    />
  );
}
