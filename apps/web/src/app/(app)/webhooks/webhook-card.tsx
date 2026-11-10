"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { Chip } from "@/components/ui/chip";
import type { Webhook, WebhookDelivery } from "@/lib/api";
import { deliveryState, eventsText, webhookState } from "@/lib/webhooks/labels";
import { deleteWebhook, resendDelivery, rotateSecret, toggleWebhook } from "./actions";
import { SecretOnce } from "./secret-once";
import { useIdempotencyKey } from "./use-key";

function when(iso: string): string {
  return new Date(iso).toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

export function WebhookCard({
  hook,
  deliveries,
}: {
  hook: Webhook;
  deliveries: WebhookDelivery[];
}) {
  const [on, setOn] = useState(hook.enabled);
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const [key, settle] = useIdempotencyKey();
  const state = webhookState({ ...hook, enabled: on });
  const heading = `hook-${hook.id}`;

  return (
    <article className="card" data-tone={state.tone} aria-labelledby={heading}>
      <div className="row-between">
        <h2 id={heading} className="t">
          {hook.name}
        </h2>
        <label className="option">
          <input
            type="checkbox"
            role="switch"
            aria-label={`${hook.name}: ${on ? "ligado" : "desligado"}`}
            checked={on}
            disabled={busy}
            onChange={(event) => {
              const next = event.currentTarget.checked;
              setOn(next);
              startTransition(async () => {
                const outcome = await toggleWebhook(hook.id, next, key());
                settle(outcome);
                setError(outcome.ok ? null : outcome.message);
                if (!outcome.ok) setOn(!next);
              });
            }}
          />
        </label>
      </div>
      <Chip tone={state.tone}>{state.label}</Chip>
      <dl className="kv">
        <dt>endereço</dt>
        <dd>{hook.url}</dd>
        <dt>eventos</dt>
        <dd>{eventsText(hook.events)}</dd>
        {hook.disabled_reason && (
          <>
            <dt>desligado</dt>
            <dd>{hook.disabled_reason}</dd>
          </>
        )}
      </dl>
      {secret && <SecretOnce secret={secret} />}
      <FormMessage error={error} />
      <div className="grid2">
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            startTransition(async () => {
              const outcome = await rotateSecret(hook.id, key());
              settle(outcome);
              setError(outcome.ok ? null : outcome.message);
              if (outcome.ok) setSecret(outcome.value.secret);
            });
          }}
        >
          Novo segredo
        </button>
        <button
          type="button"
          className="btn"
          disabled={busy}
          aria-label={`Remover ${hook.name}`}
          onClick={() => {
            startTransition(async () => {
              const outcome = await deleteWebhook(hook.id, key());
              settle(outcome);
              setError(outcome.ok ? null : outcome.message);
            });
          }}
        >
          Remover
        </button>
      </div>
      <h3 className="label">Entregas</h3>
      {deliveries.length === 0 && <p className="muted small">Nenhuma entrega ainda.</p>}
      <ul className="list" aria-label={`Entregas de ${hook.name}`}>
        {deliveries.map((delivery) => {
          const shown = deliveryState(delivery);
          return (
            <li key={delivery.id}>
              <div className="li">
                <span className="li-text">
                  <span>
                    {eventsText([delivery.event])} · {when(delivery.created_at)}
                  </span>
                  <span className="small">
                    {delivery.attempts} {delivery.attempts === 1 ? "tentativa" : "tentativas"}
                    {delivery.latency_ms !== null && ` · ${String(delivery.latency_ms)} ms`}
                    {delivery.error && ` · ${delivery.error}`}
                  </span>
                </span>
                <Chip tone={shown.tone}>{shown.label}</Chip>
                <button
                  type="button"
                  className="btn"
                  disabled={busy}
                  aria-label={`Reenviar a entrega de ${when(delivery.created_at)}`}
                  onClick={() => {
                    startTransition(async () => {
                      const outcome = await resendDelivery(delivery.id, key());
                      settle(outcome);
                      setError(outcome.ok ? null : outcome.message);
                    });
                  }}
                >
                  Reenviar
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </article>
  );
}
