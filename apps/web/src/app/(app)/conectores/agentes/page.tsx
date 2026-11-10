import Link from "next/link";
import { Chip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getMe, listAgents, type Agent } from "@/lib/api";
import { agentState, collectionsText, lastSeenText } from "@/lib/agents/labels";
import { canManage } from "@/lib/orgs/labels";
import { AgentActions } from "./agent-actions";

export const metadata = { title: "Agentes locais · Integration AI Doctor" };

// Agentes locais (#39): status, versão e último contato para todo Papel; Owner e Admin com MFA
// cadastram, renovam o token e revogam.
export default async function AgentsPage() {
  const [me, agents] = await Promise.all([getMe(), listAgents()]);
  const manager = canManage(me);
  const now = new Date();

  return (
    <>
      <div className="row-between">
        <p className="small">Coleta no SAP on-premises, só com conexões de saída.</p>
        {manager && (
          <Link className="btn primary" href="/conectores/agentes/novo">
            Adicionar
          </Link>
        )}
      </div>
      {agents === null && (
        <ErrorState title="Não foi possível carregar os agentes" action={<ReloadButton />}>
          O serviço não respondeu. Tente de novo em instantes.
        </ErrorState>
      )}
      {agents?.length === 0 && (
        <EmptyState title="Nenhum agente instalado">
          {manager
            ? "Adicione um agente para coletar IDocs, SM58 e SLG1 de um SAP sem acesso pela internet."
            : "Peça a um Owner ou Admin para instalar o agente na rede do SAP."}
        </EmptyState>
      )}
      {agents?.map((agent) => (
        <AgentCard key={agent.id} agent={agent} manager={manager} now={now} />
      ))}
    </>
  );
}

function AgentCard({ agent, manager, now }: { agent: Agent; manager: boolean; now: Date }) {
  const state = agentState(agent, now);
  const heading = `agt-${agent.id}`;
  return (
    <article className="card" data-tone={state.tone} aria-labelledby={heading}>
      <div className="row-between">
        <h2 id={heading} className="t">
          {agent.name}
        </h2>
        <Chip tone={state.tone}>{state.label}</Chip>
      </div>
      <dl className="kv">
        <dt>último contato</dt>
        <dd>{lastSeenText(agent.last_seen_at, now)}</dd>
        <dt>versão</dt>
        <dd>{agent.version ?? "—"}</dd>
        <dt>coletas</dt>
        <dd>{collectionsText(agent.config)}</dd>
        {agent.cert_fingerprint && (
          <>
            <dt>chave</dt>
            <dd>{agent.cert_fingerprint.slice(0, 16)}…</dd>
          </>
        )}
      </dl>
      {manager && (
        <AgentActions id={agent.id} name={agent.name} revoked={agent.status === "revoked"} />
      )}
    </article>
  );
}
