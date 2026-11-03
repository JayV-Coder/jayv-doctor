import Link from "next/link";
import { notFound } from "next/navigation";
import { Chip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getExecution } from "@/lib/api";
import {
  correlatedByLabel,
  errorSummary,
  eventSource,
  durationText,
  executionTitle,
  severityTone,
  statusLabel,
  timeOfDay,
} from "@/lib/executions/labels";
import { environmentLabel } from "@/lib/integrations/labels";

export const metadata = { title: "Execução · Integration AI Doctor" };

// Tela 8: Timeline da Execução. Cada Evento leva ao original (Tela 9); o que uma Regra usou como
// prova aparece destacado, com o código da Regra.
export default async function ExecutionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const execution = await getExecution(id);
  if (execution === "not_found") notFound();
  if (execution === null) {
    return (
      <ErrorState title="Não foi possível carregar a Execução" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  const keys = execution.correlation_keys;

  return (
    <>
      <Link className="small" href="/execucoes">
        ‹ Execuções
      </Link>
      <div className="row-between">
        <h2 className="title">{executionTitle(execution.id, keys)}</h2>
        {execution.incident && <Chip tone="danger">Incidente</Chip>}
      </div>
      <dl className="kv">
        <dt>integração</dt>
        <dd>
          {execution.integration_name} · {environmentLabel(execution.environment)}
        </dd>
        <dt>status</dt>
        <dd>
          {statusLabel(execution.status)}
          {execution.low_confidence && " (correlação fraca)"}
        </dd>
        {keys.trace_id?.[0] && (
          <>
            <dt>trace</dt>
            <dd>{keys.trace_id.join(", ")}</dd>
          </>
        )}
        {keys.business_reference?.[0] && (
          <>
            <dt>referência</dt>
            <dd>{keys.business_reference.join(", ")}</dd>
          </>
        )}
        <dt>duração</dt>
        <dd>{durationText(execution.duration_ms)}</dd>
      </dl>
      {execution.incident && (
        <p className="alert">
          <b>{execution.incident.title}</b> · severidade {execution.incident.severity}
        </p>
      )}

      <h2 className="label">
        {execution.events.length} {execution.events.length === 1 ? "evento" : "eventos"}{" "}
        correlacionados
      </h2>
      <ol className="timeline" aria-label="Timeline">
        {execution.events.map((event) => {
          const tone = severityTone(event.severity);
          const flagged = event.rule_codes.length > 0;
          return (
            <li key={event.id} className={flagged ? "it flagged" : "it"}>
              <span className="dot" data-tone={tone} aria-hidden="true" />
              <Link className="it-body" href={`/eventos/${event.id}`}>
                <span className="it-title">
                  {eventSource(event.source)} · {event.operation}
                </span>
                {flagged && errorSummary(event.error) && (
                  <span className="it-error">{errorSummary(event.error)}</span>
                )}
                <span className="small">
                  {timeOfDay(event.timestamp)} UTC · {event.severity} ·{" "}
                  {correlatedByLabel(event.correlated_by)}
                </span>
                {flagged && (
                  <span className="row-wrap">
                    {event.rule_codes.map((code) => (
                      <Chip key={code} tone="info">
                        {code}
                      </Chip>
                    ))}
                  </span>
                )}
              </Link>
            </li>
          );
        })}
      </ol>
      {execution.rules.length > 0 && (
        <>
          <h2 className="label">Regras que dispararam</h2>
          <ul className="list" aria-label="Regras">
            {execution.rules.map((rule) => (
              <li key={rule.rule_code}>
                <div className="li">
                  <span className="li-text">
                    <span>
                      {rule.rule_code} · {rule.category}
                    </span>
                    <span className="small">
                      {rule.description} (versão {rule.rule_version})
                    </span>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="muted small">
        Classificação por Regras determinísticas: elas apontam o sintoma, sem atribuir
        responsabilidade.
      </p>
    </>
  );
}
