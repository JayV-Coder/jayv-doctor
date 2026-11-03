"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { formatNumber } from "@/lib/format";
import { eraseSubject, findSubject, type SubjectResult } from "../mais/actions";

// A Referência (nº do pedido, CPF…) fica só na memória da página e vai no corpo da requisição.
export function SubjectForm() {
  const [reference, setReference] = useState("");
  const [found, setFound] = useState<SubjectResult | null>(null);
  const [erased, setErased] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();

  return (
    <div className="stack">
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          startTransition(async () => {
            const answer = await findSubject(reference.trim());
            setErased(null);
            if ("error" in answer) {
              setError(answer.error);
              setFound(null);
            } else {
              setError(null);
              setFound(answer.result);
            }
          });
        }}
      >
        <label className="field">
          Referência de negócio do titular
          <input
            value={reference}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => {
              setReference(event.currentTarget.value);
              setFound(null);
            }}
          />
        </label>
        <button className="btn" type="submit" disabled={busy || reference.trim() === ""}>
          Localizar
        </button>
      </form>
      <FormMessage
        error={error}
        notice={erased !== null ? `${formatNumber(erased)} Eventos apagados.` : null}
      />
      {found && (
        <section className="card" aria-label="Eventos do titular">
          <p className="small" role="status">
            {found.events === 0
              ? "Nenhum Evento com essa Referência."
              : `${formatNumber(found.events)} ${found.events === 1 ? "Evento" : "Eventos"} com essa Referência.`}
          </p>
          {found.events > 0 && (
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              onClick={() => {
                startTransition(async () => {
                  const answer = await eraseSubject(reference.trim());
                  if ("error" in answer) {
                    setError(answer.error);
                    return;
                  }
                  setErased(answer.erased);
                  setFound({ events: 0, first_seen: null, last_seen: null });
                });
              }}
            >
              Apagar esses Eventos
            </button>
          )}
        </section>
      )}
    </div>
  );
}
