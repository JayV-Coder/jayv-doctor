import Link from "next/link";
import { notFound } from "next/navigation";
import { Chip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { ListItem } from "@/components/ui/list-item";
import { ReloadButton } from "@/components/ui/reload-button";
import { getConnector, getMe, listConnectorSyncs, listIntegrations } from "@/lib/api";
import {
  checkpointText,
  connectorState,
  intervalLabel,
  lastSyncText,
  nextRunText,
  pauseText,
  syncDuration,
  syncStatus,
} from "@/lib/connectors/labels";
import { formatNumber } from "@/lib/format";
import { isManager } from "@/lib/orgs/labels";
import { ActionButton } from "../action-button";
import { LiveStatus } from "../live-status";
import { TestConnection } from "../test-connection";
import { CredentialSheet } from "./credential-sheet";
import { EditSheet } from "./edit-sheet";

export const metadata = { title: "Conector · Integration AI Doctor" };

const TIME = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "medium",
  timeZone: "UTC",
});

// Detalhe do Conector: histórico de Sincronizações e o último erro com a ação que resolve.
export default async function ConnectorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [me, connector, syncs, integrations] = await Promise.all([
    getMe(),
    getConnector(id),
    listConnectorSyncs(id),
    listIntegrations(),
  ]);
  if (connector === "not_found") notFound();
  if (connector === null) {
    return (
      <ErrorState title="Não foi possível carregar o Conector" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  const manager = isManager(me?.active_role) && me?.aal === "aal2";
  const state = connectorState(connector);
  const integration = integrations?.find(({ id }) => id === connector.integration_id);
  const now = new Date();
  const paused = connector.status === "paused";
  const active = connector.status !== "disabled";

  return (
    <>
      <LiveStatus />
      <Link className="small" href="/conectores">
        ‹ Conectores
      </Link>
      <article className="card" aria-labelledby="conector">
        <div className="row-between">
          <h2 id="conector" className="t">
            {connector.provider} · {connector.name}
          </h2>
          <Chip tone={state.tone}>{state.label}</Chip>
        </div>
        {connector.last_error && connector.status !== "active" && (
          <p className="alert">
            <b>Último erro:</b> {connector.last_error}
          </p>
        )}
        {paused && <p className="alert">{pauseText(connector.paused_reason)}</p>}
        <dl className="kv">
          <dt>integração</dt>
          <dd>{integration?.name ?? "arquivada"}</dd>
          <dt>última sync</dt>
          <dd>{lastSyncText(connector, now)}</dd>
          <dt>checkpoint</dt>
          <dd>{checkpointText(connector.checkpoint)}</dd>
          <dt>intervalo</dt>
          <dd>{intervalLabel(connector.sync_interval_seconds)}</dd>
          {active && !paused && (
            <>
              <dt>próxima</dt>
              <dd>{nextRunText(connector.next_run_at, now)}</dd>
            </>
          )}
        </dl>
        {manager && active && (
          <>
            <div className="grid2">
              <TestConnection
                id={connector.id}
                name={connector.name}
                provider={connector.provider}
              />
              <ActionButton id={connector.id} action={paused ? "resume" : "sync"} primary />
            </div>
            <div className="grid2">
              <CredentialSheet id={connector.id} provider={connector.provider} />
              <EditSheet connector={connector} />
            </div>
            {!paused && <ActionButton id={connector.id} action="pause" />}
          </>
        )}
      </article>

      <h2 className="label">Sincronizações</h2>
      {syncs === null && (
        <ErrorState title="Não foi possível carregar o histórico" action={<ReloadButton />}>
          O serviço não respondeu. Tente de novo em instantes.
        </ErrorState>
      )}
      {syncs?.length === 0 && <p className="muted small">Nenhuma Sincronização ainda.</p>}
      {syncs && syncs.length > 0 && (
        <ul className="list" aria-label="Sincronizações">
          {syncs.map((sync) => {
            const status = syncStatus(sync.status);
            return (
              <ListItem
                key={sync.id}
                title={`${TIME.format(new Date(sync.started_at))} UTC`}
                detail={[
                  syncDuration(sync.started_at, sync.finished_at),
                  `${formatNumber(sync.records)} ${sync.records === 1 ? "evento" : "eventos"}`,
                  sync.error,
                ]
                  .filter(Boolean)
                  .join(" · ")}
                trailing={<Chip tone={status.tone}>{status.label}</Chip>}
              />
            );
          })}
        </ul>
      )}
    </>
  );
}
