"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import {
  NEXT_STATUSES,
  SEVERITIES,
  severityLabel,
  statusLabel,
  type IncidentStatus,
} from "@/lib/incidents/labels";
import { changeIncident } from "../actions";

// Só as transições que o banco aceita; resolver pede a nota de resolução.
export function IncidentControls({
  id,
  status,
  severity,
  mine,
  meId,
}: {
  id: string;
  status: IncidentStatus;
  severity: string;
  mine: boolean;
  meId: string;
}) {
  const [next, setNext] = useState<IncidentStatus | "">("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();

  function apply(change: Parameters<typeof changeIncident>[1]) {
    startTransition(async () => {
      const failure = await changeIncident(id, change).catch(() => "Sem conexão. Tente de novo.");
      setError(failure);
      if (failure === null) {
        setNext("");
        setNote("");
      }
    });
  }

  return (
    <section className="card" aria-label="Ações do Incidente">
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          if (next === "") return;
          apply(next === "resolved" ? { status: next, resolution_note: note } : { status: next });
        }}
      >
        <label className="field">
          Mudar status
          <select
            value={next}
            onChange={(event) => {
              setNext(event.currentTarget.value as IncidentStatus | "");
            }}
          >
            <option value="">{statusLabel(status)} (atual)</option>
            {NEXT_STATUSES[status].map((option) => (
              <option key={option} value={option}>
                {statusLabel(option)}
              </option>
            ))}
          </select>
        </label>
        {next === "resolved" && (
          <label className="field">
            Nota de resolução
            <textarea
              rows={3}
              required
              maxLength={4000}
              value={note}
              onChange={(event) => {
                setNote(event.currentTarget.value);
              }}
            />
          </label>
        )}
        <button
          className="btn primary"
          type="submit"
          disabled={busy || next === "" || (next === "resolved" && note.trim() === "")}
        >
          Salvar status
        </button>
      </form>
      <div className="grid2">
        <label className="field">
          Severidade
          <select
            value={severity}
            disabled={busy}
            onChange={(event) => {
              apply({ severity: event.currentTarget.value });
            }}
          >
            {SEVERITIES.map((option) => (
              <option key={option} value={option}>
                {severityLabel(option)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            apply({ assignee_id: mine ? null : meId });
          }}
        >
          {mine ? "Liberar" : "Assumir"}
        </button>
      </div>
      <FormMessage error={error} />
    </section>
  );
}
