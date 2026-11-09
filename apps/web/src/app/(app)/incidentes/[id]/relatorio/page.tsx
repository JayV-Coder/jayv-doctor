import { notFound } from "next/navigation";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getMe } from "@/lib/api";
import { getDiagnosis, listDiagnoses } from "@/lib/diagnoses/api";
import { confidenceText, reviewable, verdictLabel, verdictOf } from "@/lib/diagnoses/labels";
import { formatDateTime } from "@/lib/format";
import { getIncident } from "@/lib/incidents/api";
import { incidentCode } from "@/lib/incidents/labels";
import { listReports } from "@/lib/reports/api";
import { previewName, reportLine } from "@/lib/reports/labels";
import { ReportForm } from "./report-form";
import { ShareList } from "./share-list";

export const metadata = { title: "Relatório · Integration AI Doctor" };

const OPERATORS = ["owner", "admin", "analyst"];
const HISTORY = 10;

// Tela 19: pré-visualização do que o relatório leva (o Diagnóstico atual que já terminou),
// formato e opções para quem gera; o histórico, com download, para todo Papel.
export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [incident, versions, reports, me] = await Promise.all([
    getIncident(id),
    listDiagnoses(id),
    listReports(id),
    getMe(),
  ]);
  if (incident === "not_found") notFound();
  if (incident === null || reports === null) {
    return (
      <ErrorState title="Não foi possível carregar o relatório" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  const operator = OPERATORS.includes(me?.active_role ?? "");
  const current = versions?.find((version) => reviewable(version.status));
  const diagnosis = current ? await getDiagnosis(current.id) : null;
  const recent = reports.slice(0, HISTORY);
  const verdict = verdictOf(diagnosis?.feedback);

  return (
    <>
      <section className="win" aria-label="Pré-visualização">
        <div className="win-head">
          <span>{previewName(incident.number, "pdf")}</span>
          <span className="lights" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
        </div>
        <div className="win-body report-preview">
          <span className="label">Relatório técnico</span>
          <b>
            <span className="hl">{incidentCode(incident.number)}</span> · {incident.title}
          </b>
          <span className="small">
            {formatDateTime(new Date(incident.last_seen_at), "America/Sao_Paulo")}
            {diagnosis
              ? ` · Diagnóstico v${String(diagnosis.version)} · regras ${diagnosis.ruleset_version ?? incident.rule_version}`
              : ` · regras ${incident.rule_version}`}
          </span>
          <b>❯ Resumo</b>
          <span>
            {incident.execution_count} execuções de &quot;{incident.integration_name}&quot; (
            {incident.environment})
          </span>
          {diagnosis?.status === "inconclusive" ? (
            <>
              <b>❯ Evidências insuficientes</b>
              <span>O relatório lista o que coletar.</span>
            </>
          ) : (
            <>
              <b>
                ❯ Causa provável
                {diagnosis?.confidence != null &&
                  ` · confiança heurística ${confidenceText(diagnosis.confidence)}`}
              </b>
              <span>
                {diagnosis?.probable_cause ?? "Sem Diagnóstico concluído para este Incidente."}
              </span>
            </>
          )}
          {diagnosis && (
            <>
              <b>❯ Evidências</b>
              <span>{diagnosis.evidence.length} registro(s) com id rastreável</span>
              <b>❯ Recomendações</b>
              <span>
                {diagnosis.recommendations
                  .map((item, index) => `${String(index + 1)}. ${item.text}`)
                  .join(" · ") || "—"}
              </span>
              <b>❯ Revisão humana</b>
              <span className="small">{verdict ? verdictLabel(verdict) : "○ pendente"}</span>
            </>
          )}
        </div>
      </section>

      {operator ? (
        <ReportForm incidentId={incident.id} />
      ) : (
        <p className="note">
          Seu papel baixa os relatórios já gerados; gerar fica com Analyst ou acima.
        </p>
      )}

      {recent.length > 0 && (
        <>
          <h2 className="label">Gerados</h2>
          <ul className="list" aria-label="Relatórios gerados">
            {recent.map((report) => {
              // A API traz só os links ativos, e só para quem compartilha.
              const shares = report.shares;
              return (
                <li key={report.id}>
                  <div className="li">
                    <span className="li-text">
                      <span className="row-between">
                        <span>{reportLine(report)}</span>
                        {report.status === "ready" && (
                          <a
                            className="btn"
                            href={`/incidentes/${incident.id}/relatorio/${report.id}`}
                          >
                            Baixar
                          </a>
                        )}
                      </span>
                      {shares.length > 0 && (
                        <ShareList incidentId={incident.id} reportId={report.id} shares={shares} />
                      )}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </>
  );
}
