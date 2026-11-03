import Link from "next/link";
import { Chip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getMe, listConnectors, type Connector } from "@/lib/api";
import {
  checkpointText,
  connectorState,
  lastSyncText,
  nextRunText,
  pauseText,
} from "@/lib/connectors/labels";
import { canManage } from "@/lib/orgs/labels";
import { ActionButton } from "./action-button";
import { LiveStatus } from "./live-status";
import { TestConnection } from "./test-connection";

export const metadata = { title: "Conectores · Integration AI Doctor" };

// Tela 11: um card por Conector. Todo Papel vê; só Owner e Admin com MFA agem.
export default async function ConnectorsPage() {
  const [me, connectors] = await Promise.all([getMe(), listConnectors()]);
  const manager = canManage(me);
  const now = new Date();

  return (
    <>
      <div className="row-between">
        <p className="small">Coleta autenticada de logs, com Checkpoint e retomada.</p>
        {manager && (
          <Link className="btn primary" href="/conectores/novo">
            Adicionar
          </Link>
        )}
      </div>

      {connectors === null && (
        <ErrorState title="Não foi possível carregar os Conectores" action={<ReloadButton />}>
          O serviço não respondeu. Tente de novo em instantes.
        </ErrorState>
      )}
      {connectors?.length === 0 && (
        <EmptyState title="Nenhum Conector configurado">
          {manager
            ? "Adicione um Conector do Google Cloud para coletar os logs das suas integrações."
            : "Peça a um Owner ou Admin para configurar a coleta. Enquanto isso, dá para importar um arquivo."}
        </EmptyState>
      )}
      <LiveStatus />
      {connectors?.map((connector) => (
        <ConnectorCard key={connector.id} connector={connector} manager={manager} now={now} />
      ))}

      <article className="card" aria-labelledby="importacao-manual">
        <div className="row-between">
          <h2 id="importacao-manual" className="t">
            Importação manual
          </h2>
          <Chip tone="neutral">Arquivos</Chip>
        </div>
        <p className="small">Envie logs JSON ou CSV sem Conector.</p>
        <Link className="btn" href="/importar">
          Importar arquivo
        </Link>
      </article>
      <article className="card soon" aria-labelledby="proxima-versao" aria-disabled="true">
        <div className="row-between">
          <h2 id="proxima-versao" className="t muted">
            Salesforce · SAP
          </h2>
          <Chip tone="info">v0.2</Chip>
        </div>
        <p className="small">Disponível na próxima versão.</p>
      </article>
    </>
  );
}

function ConnectorCard({
  connector,
  manager,
  now,
}: {
  connector: Connector;
  manager: boolean;
  now: Date;
}) {
  const state = connectorState(connector);
  const heading = `con-${connector.id}`;
  const paused = connector.status === "paused";
  const failing = connector.status === "failing";

  return (
    <article className="card" data-tone={state.tone} aria-labelledby={heading}>
      <div className="row-between">
        <h2 id={heading} className="t">
          {connector.provider} · {connector.name}
        </h2>
        <Chip tone={state.tone}>{state.label}</Chip>
      </div>
      {failing && connector.last_error && (
        <p className="alert">
          {connector.consecutive_failures}{" "}
          {connector.consecutive_failures === 1 ? "falha" : "falhas seguidas"}:{" "}
          {connector.last_error}
        </p>
      )}
      {paused && <p className="alert">{pauseText(connector.paused_reason)}</p>}
      <dl className="kv">
        <dt>última sync</dt>
        <dd>{lastSyncText(connector, now)}</dd>
        <dt>checkpoint</dt>
        <dd>{checkpointText(connector.checkpoint)}</dd>
        {failing && (
          <>
            <dt>próxima tentativa</dt>
            <dd>{nextRunText(connector.next_run_at, now)} (backoff)</dd>
          </>
        )}
      </dl>
      {manager && connector.status !== "disabled" && (
        <div className="grid2">
          <TestConnection
            id={connector.id}
            name={connector.name}
            provider={connector.provider}
            primary={failing}
          />
          <ActionButton
            key={paused ? "resume" : "sync"}
            id={connector.id}
            action={paused ? "resume" : "sync"}
          />
        </div>
      )}
      <Link className="btn" href={`/conectores/${connector.id}`}>
        Ver histórico
      </Link>
    </article>
  );
}
