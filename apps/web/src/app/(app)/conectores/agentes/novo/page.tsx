import Link from "next/link";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getMe, listIntegrations } from "@/lib/api";
import { canManage } from "@/lib/orgs/labels";
import { NewAgentForm } from "./new-agent-form";

export const metadata = { title: "Novo agente · Integration AI Doctor" };

export default async function NewAgentPage() {
  const [me, integrations] = await Promise.all([getMe(), listIntegrations()]);
  if (!canManage(me)) {
    return (
      <EmptyState
        title="Só Owner ou Admin instalam agentes"
        action={
          <Link className="btn" href="/conectores/agentes">
            Voltar aos agentes
          </Link>
        }
      >
        Instalar um agente exige o papel de Owner ou Admin, com verificação em duas etapas.
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
        Os Eventos coletados pelo agente pertencem a uma Integração.
      </EmptyState>
    );
  }
  return (
    <NewAgentForm
      integrations={integrations.map(({ id, name, environment }) => ({ id, name, environment }))}
    />
  );
}
