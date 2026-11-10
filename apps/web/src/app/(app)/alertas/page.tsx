import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getAlerts, getMe, listIntegrations } from "@/lib/api";
import { ruleSend, ruleWhen } from "@/lib/alerts/labels";
import { canManage } from "@/lib/orgs/labels";
import { Channels } from "./channels";
import { MyChannels } from "./my-channels";
import { NewRule } from "./new-rule";
import { RuleCard } from "./rule-card";

export const metadata = { title: "Alertas · Integration AI Doctor" };

// Tela 20 (#41): Regras com interruptor, canais da Organização e os canais e o silêncio de quem
// está olhando. Todo Papel vê as Regras; só Owner e Admin com MFA mudam.
export default async function AlertsPage() {
  const [me, alerts, integrations] = await Promise.all([getMe(), getAlerts(), listIntegrations()]);
  if (alerts === null) {
    return (
      <ErrorState title="Não foi possível carregar os alertas" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  const manager = canManage(me);
  const named = (integrations ?? []).map(({ id, name }) => ({ id, name }));

  return (
    <>
      <div className="row-between">
        <h2 className="label">Regras de alerta</h2>
        {manager && <NewRule channels={alerts.channels} />}
      </div>
      {alerts.rules.length === 0 && (
        <EmptyState title="Nenhuma regra">
          {manager
            ? "Crie uma regra, como Incidente crítico em produção, para o plantão saber no celular."
            : "Peça a um Owner ou Admin para criar as regras de alerta."}
        </EmptyState>
      )}
      {alerts.rules.map((rule) => (
        <RuleCard
          key={rule.id}
          id={rule.id}
          name={rule.name}
          enabled={rule.enabled}
          when={ruleWhen(rule.conditions, named)}
          send={ruleSend(rule.channels, alerts.channels)}
          manager={manager}
        />
      ))}
      <h2 className="label">Meus canais</h2>
      <MyChannels
        pushKey={alerts.pushKey}
        subscriptions={alerts.subscriptions}
        quiet={alerts.quiet}
      />
      {manager && (
        <>
          <h2 className="label">Canais da Organização</h2>
          <Channels channels={alerts.channels} />
        </>
      )}
    </>
  );
}
