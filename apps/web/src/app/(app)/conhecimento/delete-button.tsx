"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { deleteDocument } from "./actions";

export function DeleteButton({ id, title }: { id: string; title: string }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  return (
    <BottomSheet
      title="Remover documento"
      trigger="Remover"
      triggerLabel={`Remover ${title}`}
      onClose={() => {
        setError(null);
      }}
    >
      <p className="muted small">
        {title} sai da Base de conhecimento junto com os Fragmentos e o arquivo. Diagnósticos já
        publicados não mudam.
      </p>
      <FormMessage error={error} />
      <button
        type="button"
        className="btn primary"
        disabled={busy}
        onClick={(event) => {
          const dialog = event.currentTarget.closest("dialog");
          startTransition(async () => {
            const failure = await deleteDocument(id).catch(() => "Sem conexão. Tente de novo.");
            setError(failure);
            if (failure === null) dialog?.close();
          });
        }}
      >
        Remover
      </button>
    </BottomSheet>
  );
}
