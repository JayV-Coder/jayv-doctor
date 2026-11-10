"use client";

import { useRef, useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { deleteMapping } from "./actions";

export function DeleteMapping({
  integration,
  id,
  name,
}: {
  integration: string;
  id: string;
  name: string;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const key = useRef(crypto.randomUUID());

  return (
    <BottomSheet
      title="Remover mapa"
      trigger="Remover"
      triggerLabel={`Remover ${name}`}
      onClose={() => {
        setError(null);
      }}
    >
      <p className="muted small">
        Os Eventos que chegarem depois deixam de ser unidos por {name}. As Execuções já formadas
        continuam como estão.
      </p>
      <FormMessage error={error} />
      <button
        type="button"
        className="btn primary"
        disabled={busy}
        aria-label={`Confirmar remoção de ${name}`}
        onClick={(event) => {
          const dialog = event.currentTarget.closest("dialog");
          startTransition(async () => {
            const outcome = await deleteMapping(integration, id, key.current);
            if (outcome.ok || !outcome.offline) key.current = crypto.randomUUID();
            setError(outcome.ok ? null : outcome.message);
            if (outcome.ok) dialog?.close();
          });
        }}
      >
        Remover
      </button>
    </BottomSheet>
  );
}
