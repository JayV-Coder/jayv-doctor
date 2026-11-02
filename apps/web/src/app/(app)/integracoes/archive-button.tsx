"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { archiveIntegration } from "./actions";

export function ArchiveButton({ id, name }: { id: string; name: string }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();

  return (
    <BottomSheet title="Arquivar integração" trigger="Arquivar">
      <p className="muted small">
        {name} sai das listas e seus Conectores param de coletar. Execuções e Incidentes já
        registrados continuam guardados.
      </p>
      <FormMessage error={error} />
      <button
        type="button"
        className="btn primary"
        disabled={busy}
        aria-label={`Arquivar ${name}`}
        onClick={(event) => {
          const dialog = event.currentTarget.closest("dialog");
          startTransition(async () => {
            const failure = await archiveIntegration(id).catch(() => "Sem conexão. Tente de novo.");
            setError(failure);
            if (failure === null) dialog?.close();
          });
        }}
      >
        Arquivar
      </button>
    </BottomSheet>
  );
}
