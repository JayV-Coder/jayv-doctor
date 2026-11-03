"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { replaceCredential } from "../actions";
import { CredentialField } from "../credential-field";

export function CredentialSheet({ id, provider }: { id: string; provider: string }) {
  const [credential, setCredential] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [round, setRound] = useState(0);
  const [busy, startTransition] = useTransition();

  return (
    <BottomSheet
      title="Trocar credencial"
      trigger="Trocar credencial"
      onClose={() => {
        setCredential(null);
        setError(null);
        setRound((value) => value + 1);
      }}
    >
      <p className="muted small">
        A credencial nova substitui a anterior no cofre. Se o Conector estava pausado porque o
        provedor recusou a credencial, ele volta a coletar.
      </p>
      <CredentialField key={round} provider={provider} onChange={setCredential} />
      <FormMessage error={error} />
      <button
        type="button"
        className="btn primary"
        disabled={busy || credential === null}
        onClick={(event) => {
          const dialog = event.currentTarget.closest("dialog");
          if (credential === null) return;
          startTransition(async () => {
            const failure = await replaceCredential(id, credential).catch(
              () => "Sem conexão. Tente de novo.",
            );
            setError(failure);
            if (failure === null) dialog?.close();
          });
        }}
      >
        Salvar credencial
      </button>
    </BottomSheet>
  );
}
