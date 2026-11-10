"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { Chip } from "@/components/ui/chip";
import type { IncidentTicket } from "@/lib/api";
import { useIdempotencyKey } from "@/lib/forms/use-idempotency-key";
import { ticketText } from "@/lib/itsm/labels";
import { openTicket } from "../../chamados/actions";

// O chamado do Incidente no Jira (#43): abrir, ver a chave e o status que volta do Jira.
// Resolvido lá só sugere: quem resolve o Incidente é uma pessoa, aqui.
export function TicketCard({
  incidentId,
  tickets,
  canOpen,
  resolved,
}: {
  incidentId: string;
  tickets: IncidentTicket[];
  canOpen: boolean;
  resolved: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const [key, settle] = useIdempotencyKey();
  const ticket = tickets[0];

  return (
    <section className="card" aria-label="Chamado no Jira">
      <div className="row-between">
        <span className="t">Chamado</span>
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
      {ticket?.url && (
        <a className="small" href={ticket.url} target="_blank" rel="noreferrer">
          Abrir no Jira ↗
        </a>
      )}
      {ticket?.status === "done" && !resolved && (
        <p className="alert notice" role="status">
          Resolvido no Jira. Se o problema acabou, resolva o Incidente com a nota de resolução.
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
              const outcome = await openTicket(incidentId, key());
              settle(outcome);
              setError(outcome.ok ? null : outcome.message);
            });
          }}
        >
          {ticket ? "Tentar de novo no Jira" : "Abrir chamado no Jira"}
        </button>
      )}
    </section>
  );
}
