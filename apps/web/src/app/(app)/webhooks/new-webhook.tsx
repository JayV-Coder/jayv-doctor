"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { EVENTS } from "@/lib/webhooks/labels";
import { createWebhook } from "./actions";
import { SecretOnce } from "./secret-once";
import { useIdempotencyKey } from "@/lib/forms/use-idempotency-key";

export function NewWebhook() {
  const [error, setError] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const [key, settle] = useIdempotencyKey();

  return (
    <BottomSheet
      title="Novo webhook"
      trigger="Novo webhook"
      triggerClassName="btn primary"
      onClose={() => {
        setError(null);
        setSecret(null);
      }}
    >
      {secret ? (
        <SecretOnce secret={secret} />
      ) : (
        <form
          className="stack"
          onSubmit={(event) => {
            // `onSubmit`, não `action`: o `action` limpa o formulário, e depois de um erro a
            // pessoa perderia o que digitou.
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            startTransition(async () => {
              const outcome = await createWebhook(form, key());
              settle(outcome);
              setError(outcome.ok ? null : outcome.message);
              if (outcome.ok) setSecret(outcome.value.secret);
            });
          }}
        >
          <label className="field">
            Nome
            <input name="name" required minLength={2} maxLength={80} placeholder="ITSM" />
          </label>
          <label className="field">
            Endereço (HTTPS)
            <input
              name="url"
              type="url"
              required
              autoCapitalize="none"
              spellCheck={false}
              placeholder="https://itsm.empresa.com.br/aid"
            />
          </label>
          <fieldset className="stack">
            <legend className="label">Eventos</legend>
            {EVENTS.map((event) => (
              <label key={event.value} className="option">
                <input
                  type="checkbox"
                  name="event"
                  value={event.value}
                  defaultChecked={event.value === "incident.opened"}
                />{" "}
                {event.label}
              </label>
            ))}
          </fieldset>
          <p className="muted small">
            O corpo leva ids, títulos e links, nunca Eventos brutos. Cada entrega vai assinada.
          </p>
          <FormMessage error={error} />
          <button type="submit" className="btn primary" disabled={busy}>
            Criar webhook
          </button>
        </form>
      )}
    </BottomSheet>
  );
}
