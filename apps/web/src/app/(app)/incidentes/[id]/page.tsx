import Link from "next/link";
import { notFound } from "next/navigation";
import {
  DiagnosisCard,
  DiagnosisEvidence,
  DiagnosisHypotheses,
  DiagnosisRecommendations,
} from "@/components/diagnosis/diagnosis-card";
import { DiagnosisLive } from "@/components/diagnosis/diagnosis-live";
import { LiveRefresh } from "@/components/live-refresh";
import { Chip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { ListItem } from "@/components/ui/list-item";
import { ReloadButton } from "@/components/ui/reload-button";
import { getJira, getMe, listTickets } from "@/lib/api";
import {
  durationText,
  executionTitle,
  statusLabel as executionStatus,
} from "@/lib/executions/labels";
import { getDiagnosis, listDiagnoses } from "@/lib/diagnoses/api";
import { active, changes, reviewable, statusText } from "@/lib/diagnoses/labels";
import { formatDateTime } from "@/lib/format";
import { getIncident, listComments } from "@/lib/incidents/api";
import { incidentCode, severityLabel, severityTone, statusLabel } from "@/lib/incidents/labels";
import { environmentLabel } from "@/lib/integrations/labels";
import { CommentForm } from "./comment-form";
import { IncidentControls } from "./incident-controls";
import { TicketCard } from "./ticket-card";
import { NewDiagnosis } from "./new-diagnosis";
import { PromoteButton, ReviewControls } from "./review-controls";

export const metadata = { title: "Incidente · Integration AI Doctor" };

const OPERATORS = ["owner", "admin", "analyst"];
const ACTIONS: Record<string, string> = {
  status: "status",
  severity: "severidade",
  assignee: "responsável",
  reopened: "reaberto",
};

function historyText(entry: {
  action: string;
  from_value: string | null;
  to_value: string | null;
}) {
  if (entry.action === "assignee") return "responsável alterado";
  const label = entry.action === "severity" ? severityLabel : statusLabel;
  return `${label(entry.from_value ?? "")} → ${label(entry.to_value ?? "")}`;
}

function when(iso: string): string {
  return `${formatDateTime(new Date(iso), "UTC")} UTC`;
}

// Tela 6: Diagnóstico (versão escolhida em ?versao=, a mais nova por padrão) e revisão à
// esquerda; Evidências, Execuções, histórico e conversa à direita no desktop (≥ 1280 px).
export default async function IncidentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ versao?: string | string[] }>;
}) {
  const [{ id }, { versao }] = await Promise.all([params, searchParams]);
  const [incident, comments, me, versions, tickets, jira] = await Promise.all([
    getIncident(id),
    listComments(id),
    getMe(),
    listDiagnoses(id),
    listTickets(id),
    getJira(),
  ]);
  if (incident === "not_found") notFound();
  if (incident === null) {
    return (
      <ErrorState title="Não foi possível carregar o Incidente" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  const operator = OPERATORS.includes(me?.active_role ?? "");
  const chosen = versions?.find((item) => String(item.version) === versao) ?? versions?.[0] ?? null;
  // A anterior só serve para as diferenças, que não aparecem enquanto a escolhida roda.
  const previous =
    chosen && !active(chosen.status)
      ? versions?.find((item) => item.version === chosen.version - 1)
      : null;
  const [diagnosis, before] = await Promise.all([
    chosen ? getDiagnosis(chosen.id) : null,
    previous ? getDiagnosis(previous.id) : null,
  ]);
  const differences = diagnosis && before ? changes(before, diagnosis) : [];
  // Revisa-se a versão publicada mais nova, uma vez por revisor (o banco confere de novo).
  const newestFinal = versions?.find((item) => reviewable(item.status));
  const latest = chosen !== null && chosen.id === newestFinal?.id;
  const reviewedByMe = diagnosis?.feedback.some((item) => item.reviewer_id === me?.id) ?? false;
  const canReview =
    operator && diagnosis !== null && latest && reviewable(diagnosis.status) && !reviewedByMe;
  // A API decide pela mesma regra da promoção no banco (versão publicada mais nova).
  const canPromote = operator && incident.promotable;
  const code = incidentCode(incident.number);
  const assignee =
    incident.assignee_id === null
      ? "ninguém"
      : incident.assignee_id === me?.id
        ? "você"
        : "outro membro";

  return (
    <>
      <LiveRefresh table="incidents" id={incident.id} />
      <DiagnosisLive
        incidentId={incident.id}
        active={versions?.some((item) => active(item.status)) ?? false}
      />
      <Link className="small" href="/incidentes">
        ‹ Incidentes
      </Link>
      <div className="row-wrap">
        <Chip tone={severityTone(incident.severity)}>{severityLabel(incident.severity)}</Chip>
        <Chip tone="info">{statusLabel(incident.status)}</Chip>
        <Chip tone="neutral">
          {incident.integration_name} · {environmentLabel(incident.environment)}
        </Chip>
      </div>
      <h2 className="title">
        {code} · {incident.title}
      </h2>
      <dl className="kv">
        <dt>execuções</dt>
        <dd>{incident.execution_count}</dd>
        <dt>primeira</dt>
        <dd>{when(incident.first_seen_at)}</dd>
        <dt>última</dt>
        <dd>{when(incident.last_seen_at)}</dd>
        <dt>regra</dt>
        <dd>
          {incident.rule_version} · {incident.rule_code}
        </dd>
        <dt>responsável</dt>
        <dd>{assignee}</dd>
      </dl>
      {incident.status === "resolved" && incident.resolution_note && (
        <p className="alert notice">
          <b>Resolução:</b> {incident.resolution_note}
        </p>
      )}
      <div className="row-between">
        {operator && <NewDiagnosis incidentId={incident.id} />}
        <Link className="btn" href={`/incidentes/${incident.id}/relatorio`}>
          Relatório
        </Link>
      </div>
      {(tickets?.length || (jira?.status === "active" && jira.project_key)) && (
        <TicketCard
          incidentId={incident.id}
          tickets={tickets ?? []}
          canOpen={operator && jira?.status === "active"}
          resolved={incident.status === "resolved"}
        />
      )}
      {operator && (
        <IncidentControls
          id={incident.id}
          status={incident.status}
          severity={incident.severity}
          mine={incident.assignee_id === me?.id}
          meId={me?.id ?? ""}
        />
      )}

      <div className="incident-split">
        <div>
          {versions && versions.length > 1 && (
            <nav className="versions" aria-label="Versões do Diagnóstico">
              {versions.map((item) => (
                <Link
                  key={item.id}
                  className="chip-link"
                  aria-pressed={item.id === chosen?.id}
                  href={`/incidentes/${incident.id}?versao=${String(item.version)}`}
                >
                  v{item.version} · {statusText(item.status)}
                </Link>
              ))}
            </nav>
          )}
          {diagnosis ? (
            <DiagnosisCard diagnosis={diagnosis} />
          ) : (
            <section className="win" aria-label="Diagnóstico">
              <div className="win-head">
                <span>diagnóstico</span>
              </div>
              <div className="win-body">
                <p className="small">
                  {versions === null || chosen
                    ? "Não foi possível carregar o Diagnóstico. Tente de novo em instantes."
                    : "Ainda não há Diagnóstico. A classificação abaixo é das Regras determinísticas: aponta o sintoma, sem atribuir responsabilidade."}
                </p>
              </div>
            </section>
          )}
          {canReview && <ReviewControls incidentId={incident.id} diagnosisId={diagnosis.id} />}
          {canPromote && <PromoteButton incidentId={incident.id} />}
          {incident.knowledge_document_id && (
            <p className="note">
              Caso na <Link href="/conhecimento">Base de conhecimento</Link>: os próximos
              Diagnósticos de Incidentes semelhantes o consultam.
            </p>
          )}
          {before && diagnosis && !active(diagnosis.status) && (
            <section className="card" aria-label="Diferenças entre versões">
              <span className="label">Diferenças para a v{before.version}</span>
              {differences.length === 0 ? (
                <p className="small">Mesmo resultado da versão anterior.</p>
              ) : (
                <ul className="small">
                  {differences.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              )}
            </section>
          )}
          {diagnosis && <DiagnosisHypotheses diagnosis={diagnosis} />}
          {diagnosis && <DiagnosisRecommendations diagnosis={diagnosis} />}
        </div>
        <div>
          {diagnosis && <DiagnosisEvidence diagnosis={diagnosis} />}
          <h2 className="label">Regras que dispararam · {incident.evidence.length}</h2>
          <ul className="list" aria-label="Regras que dispararam">
            {incident.evidence.map((item) => (
              <ListItem
                key={`${item.execution_id}-${item.rule_code}-${item.rule_version}`}
                href={
                  item.matched_event_ids[0]
                    ? `/eventos/${item.matched_event_ids[0]}`
                    : `/execucoes/${item.execution_id}`
                }
                title={
                  <>
                    <Chip tone="info">{item.rule_code}</Chip> {item.description}
                  </>
                }
                detail={`${String(item.matched_event_ids.length)} ${item.matched_event_ids.length === 1 ? "Evento" : "Eventos"} · versão ${item.rule_version}`}
              />
            ))}
          </ul>

          <h2 className="label">Execuções vinculadas</h2>
          <ul className="list" aria-label="Execuções vinculadas">
            {incident.executions.map((execution) => (
              <ListItem
                key={execution.id}
                href={`/execucoes/${execution.id}`}
                title={executionTitle(execution.id, execution.correlation_keys)}
                detail={`${executionStatus(execution.status)} · ${durationText(execution.duration_ms)} · ${when(execution.first_event_at)}`}
              />
            ))}
          </ul>

          {incident.history.length > 0 && (
            <>
              <h2 className="label">Histórico</h2>
              <ul className="list" aria-label="Histórico">
                {incident.history.map((entry, index) => (
                  <ListItem
                    key={index}
                    title={`${ACTIONS[entry.action] ?? entry.action}: ${historyText(entry)}`}
                    detail={`${entry.actor_id ? (entry.actor_id === me?.id ? "você" : "membro") : "plataforma"} · ${when(entry.created_at)}${entry.note ? ` · ${entry.note}` : ""}`}
                  />
                ))}
              </ul>
            </>
          )}

          <h2 className="label">Comentários</h2>
          {comments === null && (
            <p className="muted small">Não foi possível carregar os comentários.</p>
          )}
          {comments?.length === 0 && <p className="muted small">Nenhum comentário ainda.</p>}
          {comments && comments.length > 0 && (
            <ul className="list" aria-label="Comentários">
              {comments.map((comment) => (
                <ListItem
                  key={comment.id}
                  title={comment.body_md}
                  detail={`${
                    comment.external_author
                      ? `Jira · ${comment.external_author}`
                      : comment.author_id === me?.id
                        ? "você"
                        : "membro"
                  } · ${when(comment.created_at)}`}
                />
              ))}
            </ul>
          )}
          {operator && <CommentForm id={incident.id} />}
        </div>
      </div>
    </>
  );
}
