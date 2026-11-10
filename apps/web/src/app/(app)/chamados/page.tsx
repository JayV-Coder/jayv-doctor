import Link from "next/link";
import { Chip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getJira, getMe, listWebhooks } from "@/lib/api";
import { jiraState } from "@/lib/itsm/labels";
import { canManage } from "@/lib/orgs/labels";
import { ConnectJira } from "./connect-button";
import { JiraConfig } from "./jira-config";

export const metadata = { title: "Chamados (ITSM) · Integration AI Doctor" };

// Tela 21 (#43): Jira Service Management, o webhook genérico e o que ainda não existe.
export default async function TicketsPage({
  searchParams,
}: {
  searchParams: Promise<{ jira?: string }>;
}) {
  const [{ jira: result }, me, connection] = await Promise.all([searchParams, getMe(), getJira()]);
  if (connection === undefined) {
    return (
      <ErrorState title="Não foi possível carregar os chamados" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  const manager = canManage(me);
  const hooks = manager ? await listWebhooks() : null;
  const state = jiraState(connection);

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
          <Chip tone="neutral">Em breve</Chip>
        </div>
        <div className="win-b">
          <p className="small">Cria Incident com assignment group por Sistema responsável.</p>
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
