import Link from "next/link";
import { notFound } from "next/navigation";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getEvent, getMe } from "@/lib/api";
import { sanitizationLines } from "@/lib/executions/labels";
import { EventView } from "./event-view";

export const metadata = { title: "Evento original · Integration AI Doctor" };

const SOURCES: Record<string, string> = {
  import: "Importação manual",
  connector: "Conector",
  api: "API de ingestão",
};

// Tela 9: o Evento normalizado inteiro, sem passar por texto de IA. O Log bruto (o arquivo ou
// lote de onde ele veio) é de Analyst para cima e sai por link de 5 min.
export default async function EventPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [event, me] = await Promise.all([getEvent(id), getMe()]);
  if (event === "not_found") notFound();
  if (event === null) {
    return (
      <ErrorState title="Não foi possível carregar o Evento" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  const { raw_log: raw, ...normalized } = event;
  const canDownload = ["owner", "admin", "analyst"].includes(me?.active_role ?? "");

  return (
    <>
      {event.execution_ref && (
        <Link className="small" href={`/execucoes/${event.execution_ref}`}>
          ‹ Timeline da Execução
        </Link>
      )}
      <EventView
        event={normalized}
        rawLogId={raw && canDownload ? raw.id : null}
        sanitization={sanitizationLines(event.sanitization_report)}
      />
      <section className="card" aria-labelledby="origem">
        <h2 id="origem" className="label">
          Origem
        </h2>
        {raw ? (
          <dl className="kv">
            <dt>fonte</dt>
            <dd>{SOURCES[raw.source] ?? raw.source}</dd>
            {raw.import_filename && (
              <>
                <dt>arquivo</dt>
                <dd>{raw.import_filename}</dd>
              </>
            )}
            <dt>retenção</dt>
            <dd>
              {raw.retention_days_left === 0
                ? "vence hoje"
                : `mais ${String(raw.retention_days_left)} ${raw.retention_days_left === 1 ? "dia" : "dias"}`}
            </dd>
          </dl>
        ) : (
          <p className="small">
            {canDownload
              ? "O Log bruto deste Evento já venceu pela retenção."
              : "A origem e o Log bruto ficam visíveis para Analyst, Admin e Owner."}
          </p>
        )}
      </section>
    </>
  );
}
