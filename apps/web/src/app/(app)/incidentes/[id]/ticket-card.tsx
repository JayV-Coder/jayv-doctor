"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { Chip } from "@/components/ui/chip";
import type { IncidentTicket } from "@/lib/api";
import { useIdempotencyKey } from "@/lib/forms/use-idempotency-key";
import { PROVIDERS, ticketText } from "@/lib/itsm/labels";
import { openTicket } from "../../chamados/actions";

type Provider = "jira" | "servicenow";

// Os chamados do Incidente (#43 Jira, #44 ServiceNow): um por provedor conectado, com a chave e o
// status que voltam do ITSM. Resolvido lá só sugere: quem resolve o Incidente é uma pessoa, aqui.
export function TicketCard({
  incidentId,
  tickets,
  providers,
  canOpen,
  resolved,
}: {
  incidentId: string;
  tickets: IncidentTicket[];
  // Provedores com conexão ativa nesta Organização.
  providers: Provider[];
  canOpen: boolean;
  resolved: boolean;
}) {
  const shown = [...new Set<Provider>([...tickets.map((ticket) => ticket.provider), ...providers])];
  return (
    <section className="card stack" aria-label="Chamados">
      <span className="t">Chamados</span>
      {shown.map((provider) => (
        <ProviderTicket
          key={provider}
          incidentId={incidentId}
          provider={provider}
          ticket={tickets.find((ticket) => ticket.provider === provider)}
          canOpen={canOpen && providers.includes(provider)}
          resolved={resolved}
        />
      ))}
    </section>
  );
}

function ProviderTicket({
  incidentId,
  provider,
  ticket,
  canOpen,
  resolved,
}: {
  incidentId: string;
  provider: Provider;
  ticket: IncidentTicket | undefined;
  canOpen: boolean;
  resolved: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const [key, settle] = useIdempotencyKey();
  const name = PROVIDERS[provider] ?? provider;

  return (
    <div className="stack" aria-label={`Chamado no ${name}`} role="group">
      <div className="row-between">
        <span className="small">{name}</span>
        {ticket && (
          <Chip
            tone={
              ticket.status === "failed" ? "danger" : ticket.status === "done" ? "success" : "info"
            }
          >
            {ticketText(ticket)}
          </Chip>
        )}
      </div>
      {ticket?.assignment_group && <p className="muted small">Grupo: {ticket.assignment_group}</p>}
      {ticket?.url && (
        <a className="small" href={ticket.url} target="_blank" rel="noreferrer">
          Abrir no {name} ↗
        </a>
      )}
      {ticket?.status === "done" && !resolved && (
        <p className="alert notice" role="status">
          Resolvido no {name}. Se o problema acabou, resolva o Incidente com a nota de resolução.
        </p>
      )}
      <FormMessage error={error} />
      {canOpen && (!ticket || ticket.status === "failed") && (
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            startTransition(async () => {
              const outcome = await openTicket(incidentId, provider, key());
              settle(outcome);
              setError(outcome.ok ? null : outcome.message);
            });
          }}
        >
          {ticket ? `Tentar de novo no ${name}` : `Abrir chamado no ${name}`}
        </button>
      )}
    </div>
  );
}
