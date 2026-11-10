import Link from "next/link";
import { Chip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getJira, getMe, getServiceNow, listWebhooks } from "@/lib/api";
import { jiraState, serviceNowState } from "@/lib/itsm/labels";
import { canManage } from "@/lib/orgs/labels";
import { ConnectJira } from "./connect-button";
import { JiraConfig } from "./jira-config";
import { ServiceNowConfig } from "./servicenow-config";

export const metadata = { title: "Chamados (ITSM) · Integration AI Doctor" };

// Tela 21 (#43, #44): Jira Service Management, ServiceNow e o webhook genérico.
export default async function TicketsPage({
  searchParams,
}: {
  searchParams: Promise<{ jira?: string }>;
}) {
  const [{ jira: result }, me, connection, servicenow] = await Promise.all([
    searchParams,
    getMe(),
    getJira(),
    getServiceNow(),
  ]);
  if (connection === undefined || servicenow === undefined) {
    return (
      <ErrorState title="Não foi possível carregar os chamados" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  const manager = canManage(me);
  const hooks = manager ? await listWebhooks() : null;
  const state = jiraState(connection);
  const serviceNow = serviceNowState(servicenow);

  return (
    <>
      {result === "conectado" && (
        <p className="alert notice" role="status">
          Jira autorizado. Escolha o site e o projeto.
        </p>
      )}
      {result === "erro" && (
        <p className="alert" role="alert">
          O Jira não foi conectado. Tente de novo.
        </p>
      )}
      <section className="win" aria-label="Jira Service Management">
        <div className="win-h">
          <span>jira service management</span>
          <Chip tone={state.tone}>{state.label}</Chip>
        </div>
        <div className="win-b stack">
          {connection?.project_key && (
            <dl className="kv">
              <dt>projeto</dt>
              <dd>
                {connection.project_key} · {connection.issue_type}
              </dd>
              <dt>conteúdo</dt>
              <dd>resumo e link do Diagnóstico</dd>
            </dl>
          )}
          {connection?.last_error && <p className="alert">{connection.last_error}</p>}
          {manager && (!connection || connection.status === "needs_reauth") && (
            <ConnectJira label={connection ? "Conectar de novo" : "Conectar Jira"} />
          )}
          {manager && connection && connection.status !== "needs_reauth" && (
            <JiraConfig connection={connection} />
          )}
          {!manager && !connection && (
            <p className="muted small">Peça a um Owner ou Admin para conectar o Jira.</p>
          )}
        </div>
      </section>
      <section className="win" aria-label="ServiceNow">
        <div className="win-h">
          <span>servicenow</span>
          <Chip tone={serviceNow.tone}>{serviceNow.label}</Chip>
        </div>
        <div className="win-b stack">
          {servicenow?.instance_url && (
            <dl className="kv">
              <dt>instância</dt>
              <dd>{servicenow.instance_url.replace("https://", "")}</dd>
              <dt>grupo</dt>
              <dd>por Sistema responsável</dd>
            </dl>
          )}
          {servicenow?.last_error && <p className="alert">{servicenow.last_error}</p>}
          {manager ? (
            <ServiceNowConfig connection={servicenow ?? null} />
          ) : (
            !servicenow && (
              <p className="muted small">Peça a um Owner ou Admin para conectar o ServiceNow.</p>
            )
          )}
        </div>
      </section>
      <section className="win" aria-label="Webhook genérico">
        <div className="win-h">
          <span>webhook genérico</span>
          {hooks && (
            <Chip tone={hooks.some((hook) => hook.enabled) ? "success" : "neutral"}>
              {hooks.filter((hook) => hook.enabled).length} ativo(s)
            </Chip>
          )}
        </div>
        <div className="win-b stack">
          <p className="small">Eventos assinados (HMAC-SHA256) para qualquer sistema.</p>
          {manager && (
            <Link className="btn" href="/webhooks">
              Ver webhooks
            </Link>
          )}
        </div>
      </section>
    </>
  );
}
