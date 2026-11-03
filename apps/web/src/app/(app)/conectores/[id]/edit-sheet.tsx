"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import type { Connector } from "@/lib/api";
import { INTERVALS, intervalLabel } from "@/lib/connectors/labels";
import { editConnector } from "../actions";

export function EditSheet({ connector }: { connector: Connector }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  // O intervalo salvo pode não estar entre os oferecidos (a API aceita de 60 s a 1 dia).
  const intervals = INTERVALS.includes(
    connector.sync_interval_seconds as (typeof INTERVALS)[number],
  )
    ? INTERVALS
    : [...INTERVALS, connector.sync_interval_seconds];

  return (
    <BottomSheet
      title="Editar conector"
      trigger="Editar"
      onClose={() => {
        setError(null);
      }}
    >
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          const form = event.currentTarget;
          startTransition(async () => {
            const failure = await editConnector(connector.id, new FormData(form)).catch(
              () => "Sem conexão. Tente de novo.",
            );
            setError(failure);
            if (failure === null) form.closest("dialog")?.close();
          });
        }}
      >
        <label className="field">
          Nome
          <input name="name" required minLength={2} maxLength={80} defaultValue={connector.name} />
        </label>
        <label className="field">
          Intervalo
          <select name="sync_interval_seconds" defaultValue={connector.sync_interval_seconds}>
            {intervals.map((seconds) => (
              <option key={seconds} value={seconds}>
                {intervalLabel(seconds)}
              </option>
            ))}
          </select>
        </label>
        <FormMessage error={error} />
        <button className="btn primary" type="submit" disabled={busy}>
          Salvar
        </button>
      </form>
    </BottomSheet>
  );
}
