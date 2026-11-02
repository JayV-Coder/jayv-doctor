import { BottomSheet } from "@/components/ui/bottom-sheet";
import { Chip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getMe, listIntegrations } from "@/lib/api";
import {
  environmentLabel,
  environmentTone,
  errorRateText,
  flowLabel,
} from "@/lib/integrations/labels";
import { isManager } from "@/lib/orgs/labels";
import { ArchiveButton } from "./archive-button";
import { IntegrationForm } from "./integration-form";

export const metadata = { title: "Integrações · Integration AI Doctor" };

// Tela 10: lista em cards; o cadastro abre numa folha inferior.
export default async function IntegrationsPage() {
  const [me, integrations] = await Promise.all([getMe(), listIntegrations()]);
  // Toda escrita exige MFA: sem `aal2`, o formulário só levaria a um erro no fim.
  const manager = isManager(me?.active_role) && me?.aal === "aal2";

  return (
    <>
      <div className="row-between">
        <p className="small">
          Fluxos de negócio monitorados. Cada Execução e Incidente pertence a uma Integração.
        </p>
        {manager && (
          <BottomSheet title="Nova integração" trigger="Nova" triggerClassName="btn primary">
            <IntegrationForm />
          </BottomSheet>
        )}
      </div>

      {integrations === null && (
        <ErrorState title="Não foi possível carregar as Integrações" action={<ReloadButton />}>
          O serviço não respondeu. Tente de novo em instantes.
        </ErrorState>
      )}
      {integrations?.length === 0 && (
        <EmptyState title="Nenhuma Integração cadastrada">
          {manager
            ? "Cadastre o primeiro fluxo, como Pedidos Salesforce → SAP, para organizar a coleta e os Incidentes."
            : "Peça a um Owner ou Admin para cadastrar os fluxos que sua equipe sustenta."}
        </EmptyState>
      )}
      {integrations?.map((integration) => (
        <article key={integration.id} className="card" aria-labelledby={`int-${integration.id}`}>
          <div className="row-between">
            <h2 id={`int-${integration.id}`} className="t">
              {integration.name}
            </h2>
            <Chip tone={environmentTone(integration.environment)}>
              {environmentLabel(integration.environment)}
            </Chip>
          </div>
          <dl className="kv">
            <dt>erro 24 h</dt>
            <dd>{errorRateText(integration.error_rate_24h)}</dd>
            <dt>fluxo</dt>
            <dd>{flowLabel(integration.source_system, integration.target_system)}</dd>
            {integration.owner_team && (
              <>
                <dt>time</dt>
                <dd>{integration.owner_team}</dd>
              </>
            )}
          </dl>
          {integration.description && <p className="small">{integration.description}</p>}
          {manager && <ArchiveButton id={integration.id} name={integration.name} />}
        </article>
      ))}
    </>
  );
}
