"use client";

import { useRef, useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { createChannel, deleteChannel } from "./actions";
import { useIdempotencyKey } from "@/lib/forms/use-idempotency-key";

const KINDS: Record<string, string> = {
  webpush: "Push",
  email: "E-mail",
  slack: "Slack",
  teams: "Microsoft Teams",
  jira: "Jira (abre o chamado)",
  servicenow: "ServiceNow (abre o incident)",
};

// Canais da Organização (gestores): o webhook do Slack ou do Teams vai para o Vault e não volta.
export function Channels({
  channels,
}: {
  channels: { id: string; type: string; name: string; config: Record<string, unknown> }[];
}) {
  const [type, setType] = useState("webpush");
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const [key, settle] = useIdempotencyKey();
  const formRef = useRef<HTMLFormElement>(null);

  return (
    <>
      <ul className="list" aria-label="Canais da Organização">
        {channels.map((channel) => (
          <li key={channel.id}>
            <div className="li">
              <span className="li-text">
                <span>{channel.name}</span>
                <span className="small">
                  {KINDS[channel.type] ?? channel.type}
                  {channel.config.audience === "all"
                    ? " · todos da Organização"
                    : channel.config.audience
                      ? " · Owners e Admins"
                      : ""}
                </span>
              </span>
              <button
                type="button"
                className="btn"
                disabled={busy}
                aria-label={`Remover o canal ${channel.name}`}
                onClick={() => {
                  startTransition(async () => {
                    const outcome = await deleteChannel(channel.id, key());
                    settle(outcome);
                    setError(outcome.ok ? null : outcome.message);
                  });
                }}
              >
                Remover
              </button>
            </div>
          </li>
        ))}
      </ul>
      <FormMessage error={error} />
      <BottomSheet
        title="Novo canal"
        trigger="Novo canal"
        onClose={() => {
          setError(null);
        }}
      >
        <form
          ref={formRef}
          className="stack"
          onSubmit={(event) => {
            // `onSubmit`, não `action`: o `action` limpa o formulário, e depois de um erro a
            // pessoa perderia o que digitou.
            event.preventDefault();
            const element = event.currentTarget;
            const form = new FormData(element);
            startTransition(async () => {
              const outcome = await createChannel(form, key());
              settle(outcome);
              setError(outcome.ok ? null : outcome.message);
              if (outcome.ok) {
                // Sem o reset do `action`: limpa à mão (o webhook não fica no formulário).
                element.reset();
                formRef.current?.closest("dialog")?.close();
              }
            });
          }}
        >
          <label className="field">
            Tipo
            <select
              name="type"
              value={type}
              onChange={(event) => {
                setType(event.currentTarget.value);
              }}
            >
              {Object.entries(KINDS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Nome
            <input name="name" required minLength={2} maxLength={80} placeholder="Plantão" />
          </label>
          {type === "slack" || type === "teams" ? (
            <label className="field">
              Endereço do webhook
              <input
                name="webhook"
                type="url"
                required
                autoCapitalize="none"
                spellCheck={false}
                placeholder={
                  type === "slack"
                    ? "https://hooks.slack.com/services/…"
                    : "https://….webhook.office.com/…"
                }
              />
            </label>
          ) : type === "jira" || type === "servicenow" ? (
            <p className="muted small">
              Abre um chamado por Incidente no {type === "jira" ? "Jira" : "ServiceNow"} configurado
              em Chamados (ITSM).
            </p>
          ) : (
            <label className="field">
              Quem recebe
              <select name="audience" defaultValue="managers">
                <option value="managers">Owners e Admins</option>
                <option value="all">Todos da Organização</option>
              </select>
            </label>
          )}
          <p className="muted small">
            A mensagem leva só o título, a severidade, a Integração e o link do Incidente.
          </p>
          <FormMessage error={error} />
          <button type="submit" className="btn primary" disabled={busy}>
            Salvar canal
          </button>
        </form>
      </BottomSheet>
    </>
  );
}
