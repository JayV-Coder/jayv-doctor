import Link from "next/link";
import { Chip } from "@/components/ui/chip";
import { ConfidenceBar } from "@/components/ui/confidence-bar";
import {
  active,
  confidenceText,
  evidenceChip,
  evidenceHref,
  modeLabel,
  reviewTime,
  stageSteps,
  statusChip,
  systemLabel,
  verdictLabel,
} from "@/lib/diagnoses/labels";
import type { DiagnosisDetail } from "@/lib/diagnoses/api";

type Props = { diagnosis: DiagnosisDetail };

// Card de Diagnóstico da Tela 6. Inconclusivo não afirma Causa provável; IA que falhou avisa que o
// resultado é só das Regras. A Confiança é heurística e aparece sempre com esse rótulo.
export function DiagnosisCard({ diagnosis }: Props) {
  const chip = statusChip(diagnosis);
  const header = `diagnóstico v${String(diagnosis.version)} · ${modeLabel(diagnosis.mode)}`;
  return (
    <section className="win" aria-label="Diagnóstico">
      <div className="win-head">
        <span>{header}</span>
        <Chip tone={chip.tone}>{chip.text}</Chip>
      </div>
      <div className="win-body stack">
        {active(diagnosis.status) ? (
          <Progress diagnosis={diagnosis} />
        ) : diagnosis.status === "failed" ? (
          <p className="alert" role="alert">
            O Diagnóstico não pôde rodar:{" "}
            {(diagnosis.error ?? "erro desconhecido").replace(/\.$/, "")}. Peça um novo.
          </p>
        ) : (
          <Result diagnosis={diagnosis} />
        )}
      </div>
    </section>
  );
}

function Progress({ diagnosis }: Props) {
  const steps = stageSteps(
    diagnosis.stage,
    diagnosis.requested_mode,
    diagnosis.include_knowledge_base,
  );
  const current = steps.find((step) => step.state === "current");
  return (
    <>
      <p className="small" role="status">
        {diagnosis.status === "queued" ? "Na fila…" : `${current?.label ?? "Processando"}…`}
      </p>
      <ol className="steps" aria-label="Etapas do Diagnóstico">
        {steps.map((step) => (
          <li
            key={step.label}
            data-state={step.state}
            aria-current={step.state === "current" ? "step" : undefined}
          >
            {step.label}
          </li>
        ))}
      </ol>
    </>
  );
}

function Result({ diagnosis }: Props) {
  const inconclusive = diagnosis.status === "inconclusive";
  const correction = diagnosis.feedback.find((item) => item.verdict === "corrected");
  return (
    <>
      {correction && (
        <div className="note">
          <span className="label">Corrigido pela revisão</span>
          {correction.correct_category && <p className="small">{correction.correct_category}</p>}
          {correction.correct_cause && <p className="cause">{correction.correct_cause}</p>}
        </div>
      )}
      {diagnosis.status === "failed_llm" && (
        <p className="alert" role="status">
          O modelo de IA falhou: este Diagnóstico foi montado só com as Regras determinísticas.
        </p>
      )}
      {inconclusive ? (
        <>
          <span className="label">Evidências insuficientes</span>
          <p className="small">
            Não há Evidência do próprio Incidente que sustente uma causa. Colete os logs do sistema
            de destino no horário da falha (ou conecte a fonte que falta) e peça um novo
            Diagnóstico.
          </p>
        </>
      ) : (
        <>
          <span className="label">Causa provável</span>
          <p className="cause">{diagnosis.probable_cause ?? "—"}</p>
        </>
      )}
      {diagnosis.confidence !== null && (
        <ConfidenceBar
          value={diagnosis.confidence}
          label="Confiança heurística (não calibrada)"
          decimal
        />
      )}
      <dl className="kv">
        <dt>sistema</dt>
        <dd>{systemLabel(diagnosis.responsible_system)}</dd>
        {diagnosis.classification && (
          <>
            <dt>classificação</dt>
            <dd>{diagnosis.classification}</dd>
          </>
        )}
        <dt>regras</dt>
        <dd>{diagnosis.ruleset_version ?? "—"}</dd>
        {diagnosis.model && (
          <>
            <dt>modelo</dt>
            <dd>{diagnosis.model}</dd>
          </>
        )}
      </dl>
      {diagnosis.feedback.length > 0 && (
        <ul className="small reviews" aria-label="Revisões">
          {diagnosis.feedback.map((item) => (
            <li key={item.id}>
              {verdictLabel(item.verdict)}
              {item.time_to_review_s !== null && ` · ${reviewTime(item.time_to_review_s)}`}
              {item.comment && ` · ${item.comment}`}
            </li>
          ))}
        </ul>
      )}
      {diagnosis.verification_notes.length > 0 && (
        <details className="notes">
          <summary className="small">
            Verificação · {diagnosis.verification_notes.length}{" "}
            {diagnosis.verification_notes.length === 1 ? "nota" : "notas"}
          </summary>
          <ul className="small">
            {diagnosis.verification_notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

export function DiagnosisEvidence({ diagnosis }: Props) {
  if (active(diagnosis.status)) return null;
  return (
    <>
      <h2 className="label">Evidências · {diagnosis.evidence.length}</h2>
      {diagnosis.evidence.length === 0 ? (
        <p className="muted small">Nenhuma Evidência neste Diagnóstico.</p>
      ) : (
        <ul className="list" aria-label="Evidências do Diagnóstico">
          {diagnosis.evidence.map((item) => {
            const href = evidenceHref(item);
            const body = (
              <>
                <Chip tone={item.kind === "rule_match" ? "info" : "neutral"}>
                  {evidenceChip(item)}
                </Chip>
                <span className="li-text">
                  <span>{item.finding}</span>
                  <span className="small">{item.label}</span>
                </span>
              </>
            );
            return (
              <li key={item.rank}>
                {href ? (
                  <Link className="li" href={href}>
                    {body}
                    <span aria-hidden="true">›</span>
                  </Link>
                ) : (
                  <div className="li">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}

export function DiagnosisHypotheses({ diagnosis }: Props) {
  if (diagnosis.hypotheses.length === 0) return null;
  const items = (
    <ol className="list" aria-label="Hipóteses">
      {diagnosis.hypotheses.map((item) => (
        <li key={item.rank}>
          <div className="li">
            <span className="small">{String(item.rank).padStart(2, "0")}</span>
            <span className="li-text">
              <span>{item.statement}</span>
            </span>
            <Chip tone={item.rank === 1 ? "warning" : "neutral"}>
              {confidenceText(item.confidence)} · heurística
            </Chip>
          </div>
        </li>
      ))}
    </ol>
  );
  return (
    <>
      {/* Celular: expansível; desktop: seção própria. */}
      <details className="mobile-only">
        <summary className="label">Hipóteses · {diagnosis.hypotheses.length}</summary>
        {items}
      </details>
      <section className="desktop-only" aria-label="Hipóteses do Diagnóstico">
        <h2 className="label">Hipóteses</h2>
        {items}
      </section>
    </>
  );
}

// Sempre ações humanas: numeradas, sem botão de execução.
export function DiagnosisRecommendations({ diagnosis }: Props) {
  if (diagnosis.recommendations.length === 0) return null;
  return (
    <>
      <h2 className="label">Recomendações</h2>
      <ol className="card recommendations" aria-label="Recomendações">
        {diagnosis.recommendations.map((item) => (
          <li key={item.rank}>{item.text}</li>
        ))}
      </ol>
    </>
  );
}
