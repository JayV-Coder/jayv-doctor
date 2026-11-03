"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import type { EventDetail } from "@/lib/api";
import { highlightJson } from "@/lib/executions/labels";
import { rawLogUrl } from "../../execucoes/actions";

export function EventView({
  event,
  rawLogId,
  sanitization,
}: {
  event: Omit<EventDetail, "raw_log">;
  rawLogId: string | null;
  sanitization: string[];
}) {
  const [tab, setTab] = useState<"normalized" | "raw">("normalized");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const json = JSON.stringify(event, null, 2);

  return (
    <>
      <div className="row-between">
        <h2 className="title ell">{event.operation}</h2>
        <button
          type="button"
          className="btn"
          onClick={() => {
            void navigator.clipboard.writeText(json).then(() => {
              setCopied(true);
            });
          }}
        >
          {copied ? "Copiado" : "Copiar"}
        </button>
      </div>
      <div className="segmented two" role="tablist" aria-label="Formato">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "normalized"}
          onClick={() => {
            setTab("normalized");
          }}
        >
          Normalizado
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "raw"}
          onClick={() => {
            setTab("raw");
          }}
        >
          Log bruto
        </button>
      </div>
      {tab === "normalized" ? (
        <section className="win" aria-label="Evento normalizado">
          <div className="win-head">
            <span>event.v1.json</span>
          </div>
          <pre className="code">
            {highlightJson(event).map((token, index) =>
              token.kind === "plain" ? (
                token.text
              ) : (
                <span key={index} className={`j-${token.kind}`}>
                  {token.text}
                </span>
              ),
            )}
          </pre>
        </section>
      ) : (
        <section className="card" aria-label="Log bruto">
          <p className="small">
            O Log bruto é o arquivo ou lote inteiro de onde este Evento saiu, antes da Sanitização.
            Ele não é exibido aqui: baixe pelo link, que vale 5 minutos e fica registrado na
            auditoria.
          </p>
          <FormMessage error={error} />
          {rawLogId ? (
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              onClick={() => {
                startTransition(async () => {
                  const url = await rawLogUrl(rawLogId).catch(() => null);
                  if (url === null) {
                    setError("Não foi possível gerar o link agora.");
                    return;
                  }
                  window.location.assign(url);
                });
              }}
            >
              Baixar Log bruto (link de 5 min)
            </button>
          ) : (
            <p className="muted small">Disponível para Analyst, Admin e Owner.</p>
          )}
        </section>
      )}
      <section className="card checklist" aria-label="Sanitização aplicada">
        <span className="label">Sanitização aplicada</span>
        {sanitization.map((line) => (
          <span key={line}>{line}</span>
        ))}
      </section>
    </>
  );
}
