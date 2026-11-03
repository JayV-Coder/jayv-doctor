import Link from "next/link";
import { notFound } from "next/navigation";
import { LiveRefresh } from "@/components/live-refresh";
import { Chip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { ListItem } from "@/components/ui/list-item";
import { ReloadButton } from "@/components/ui/reload-button";
import { getMe } from "@/lib/api";
import {
  durationText,
  executionTitle,
  statusLabel as executionStatus,
} from "@/lib/executions/labels";
import { formatDateTime } from "@/lib/format";
import { getIncident, listComments } from "@/lib/incidents/api";
import { incidentCode, severityLabel, severityTone, statusLabel } from "@/lib/incidents/labels";
import { environmentLabel } from "@/lib/integrations/labels";
import { CommentForm } from "./comment-form";
import { IncidentControls } from "./incident-controls";

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

// Base da Tela 6: o Diagnóstico com IA entra no #25; aqui ficam o fluxo, as Evidências das
// Regras, as Execuções e a conversa da equipe.
export default async function IncidentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [incident, comments, me] = await Promise.all([getIncident(id), listComments(id), getMe()]);
  if (incident === "not_found") notFound();
  if (incident === null) {
    return (
      <ErrorState title="Não foi possível carregar o Incidente" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  const operator = OPERATORS.includes(me?.active_role ?? "");
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
      {operator && (
        <IncidentControls
          id={incident.id}
          status={incident.status}
          severity={incident.severity}
          mine={incident.assignee_id === me?.id}
          meId={me?.id ?? ""}
        />
      )}

      <section className="win" aria-label="Diagnóstico">
        <div className="win-head">
          <span>diagnóstico</span>
        </div>
        <div className="win-body">
          <p className="small">
            Ainda não há Diagnóstico. A classificação abaixo é das Regras determinísticas: aponta o
            sintoma, sem atribuir responsabilidade.
          </p>
        </div>
      </section>

      <h2 className="label">Evidências · {incident.evidence.length}</h2>
      <ul className="list" aria-label="Evidências">
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
              detail={`${comment.author_id === me?.id ? "você" : "membro"} · ${when(comment.created_at)}`}
            />
          ))}
        </ul>
      )}
      {operator && <CommentForm id={incident.id} />}
    </>
  );
}
