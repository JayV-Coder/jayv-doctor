"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { deleteRule, toggleRule } from "./actions";
import { useIdempotencyKey } from "./use-key";

export function RuleCard({
  id,
  name,
  enabled,
  when,
  send,
  manager,
}: {
  id: string;
  name: string;
  enabled: boolean;
  when: string;
  send: string;
  manager: boolean;
}) {
  // Otimista: muda na hora e volta se a API recusar.
  const [on, setOn] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const [key, settle] = useIdempotencyKey();
  const heading = `rule-${id}`;

  return (
    <article className="card" aria-labelledby={heading}>
      <div className="row-between">
        <h2 id={heading} className={on ? "t" : "t muted"}>
          {name}
        </h2>
        <label className="option">
          <input
            type="checkbox"
            role="switch"
            aria-label={`${name}: ${on ? "ligada" : "desligada"}`}
            checked={on}
            disabled={!manager || busy}
            onChange={(event) => {
              const next = event.currentTarget.checked;
              setOn(next);
              startTransition(async () => {
                const outcome = await toggleRule(id, next, key());
                settle(outcome);
                setError(outcome.ok ? null : outcome.message);
                if (!outcome.ok) setOn(!next);
              });
            }}
          />
        </label>
      </div>
      <dl className="kv">
        <dt>quando</dt>
        <dd>{when}</dd>
        <dt>enviar</dt>
        <dd>{send}</dd>
      </dl>
      <FormMessage error={error} />
      {manager && (
        <button
          type="button"
          className="btn"
          disabled={busy}
          aria-label={`Remover ${name}`}
          onClick={() => {
            startTransition(async () => {
              const outcome = await deleteRule(id, key());
              settle(outcome);
              setError(outcome.ok ? null : outcome.message);
            });
          }}
        >
          Remover
        </button>
      )}
    </article>
  );
}
