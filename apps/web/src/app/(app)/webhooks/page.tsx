import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getMe, listWebhookDeliveries, listWebhooks } from "@/lib/api";
import { canManage } from "@/lib/orgs/labels";
import { NewWebhook } from "./new-webhook";
import { WebhookCard } from "./webhook-card";

export const metadata = { title: "Webhooks · Integration AI Doctor" };

// Webhooks de saída (#42): só Owner e Admin com MFA. Cada card mostra o estado, os eventos e
// as últimas entregas, com "Reenviar".
export default async function WebhooksPage() {
  const me = await getMe();
  if (!canManage(me)) {
    return (
      <EmptyState title="Só Owner ou Admin configuram webhooks">
        Configurar webhooks exige o papel de Owner ou Admin, com verificação em duas etapas.
      </EmptyState>
    );
  }
  const hooks = await listWebhooks();
  if (hooks === null) {
    return (
      <ErrorState title="Não foi possível carregar os webhooks" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  const deliveries = await Promise.all(hooks.map((hook) => listWebhookDeliveries(hook.id)));

  return (
    <>
      <div className="row-between">
        <p className="small">Eventos do Doctor no seu ITSM ou automação, assinados.</p>
        <NewWebhook />
      </div>
      {hooks.length === 0 && (
        <EmptyState title="Nenhum webhook">
          Cadastre um endereço HTTPS para receber Incidentes e Diagnósticos no seu sistema.
        </EmptyState>
      )}
      {hooks.map((hook, index) => (
        <WebhookCard key={hook.id} hook={hook} deliveries={deliveries[index] ?? []} />
      ))}
    </>
  );
}
