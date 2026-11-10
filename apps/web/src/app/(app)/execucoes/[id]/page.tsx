import Link from "next/link";
import { notFound } from "next/navigation";
import type { CSSProperties } from "react";
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
import { crossKeysText, laneOf, lanes } from "@/lib/executions/lanes";
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
  // Resolvido ou descartado não é problema ativo.
  const active = ["open", "investigating"].includes(execution.incident?.status ?? "");
  // Raias por sistema quando a Execução passa por mais de um (#40).
  const systems = lanes(execution.events);
  const laned = systems.length > 1;
  const laneStyle = { "--lanes": String(systems.length) } as CSSProperties;

  return (
    <>
      <Link className="small" href="/execucoes">
        ‹ Execuções
      </Link>
      <div className="row-between">
        <h2 className="title">{executionTitle(execution.id, keys)}</h2>
        {active && <Chip tone="danger">Incidente</Chip>}
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
        {keys.cross_system?.[0] && (
          <>
            <dt>entre sistemas</dt>
            <dd>{crossKeysText(keys.cross_system)}</dd>
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
      {active && execution.incident && (
        <p className="alert">
          <b>{execution.incident.title}</b> · severidade {execution.incident.severity}
        </p>
      )}

      <h2 className="label">
        {execution.events.length} {execution.events.length === 1 ? "evento" : "eventos"}{" "}
        correlacionados
      </h2>
      {laned && (
        <div className="lanes-head" style={laneStyle} aria-hidden="true">
          {systems.map((lane) => (
            <span key={lane.system} title={lane.label}>
              {lane.short}
            </span>
          ))}
        </div>
      )}
      <ol
        className={laned ? "timeline lanes" : "timeline"}
        style={laned ? laneStyle : undefined}
        aria-label={
          laned ? `Timeline em raias: ${systems.map((l) => l.label).join(", ")}` : "Timeline"
        }
      >
        {execution.events.map((event) => {
          const tone = severityTone(event.severity);
          const flagged = event.rule_codes.length > 0;
          const mine = laneOf(event);
          return (
            <li key={event.id} className={flagged ? "it flagged" : "it"}>
              {laned ? (
                <span className="lane-rail" aria-hidden="true">
                  {systems.map((lane) => (
                    <span key={lane.system} className="lane-cell">
                      {lane.system === mine && <span className="dot" data-tone={tone} />}
                    </span>
                  ))}
                </span>
              ) : (
                <span className="dot" data-tone={tone} aria-hidden="true" />
              )}
              <Link
                className="it-body"
                href={`/eventos/${event.id}?em=${encodeURIComponent(event.timestamp)}`}
              >
                <span className="it-title">
                  {eventSource(event.source)} · {event.operation}
                </span>
                {flagged && errorSummary(event.error) && (
                  <span className="it-error">{errorSummary(event.error)}</span>
                )}
                <span className="small">
                  {laned && `${systems.find((lane) => lane.system === mine)?.label ?? mine} · `}
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
