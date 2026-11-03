"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { testSavedConnection, type TestOutcome } from "./actions";
import { CredentialField } from "./credential-field";

export function TestConnection({
  id,
  name,
  provider,
  primary = false,
}: {
  id: string;
  name: string;
  provider: string;
  primary?: boolean;
}) {
  const [credential, setCredential] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<TestOutcome | null>(null);
  const [busy, startTransition] = useTransition();
  // Remonta o campo a cada abertura: a chave escolhida antes não fica no formulário.
  const [round, setRound] = useState(0);

  return (
    <BottomSheet
      title={`Testar conexão · ${name}`}
      trigger="Testar conexão"
      triggerClassName={primary ? "btn primary" : "btn"}
      onClose={() => {
        setCredential(null);
        setOutcome(null);
        setRound((value) => value + 1);
      }}
    >
      <p className="muted small">
        A credencial salva fica no cofre e não sai de lá. Para testar, envie a credencial de novo:
        ela é usada só neste teste e descartada.
      </p>
      <CredentialField key={round} provider={provider} onChange={setCredential} />
      <FormMessage
        error={outcome && !outcome.ok ? outcome.message : null}
        notice={outcome?.ok ? outcome.message : null}
      />
      <button
        type="button"
        className="btn primary"
        disabled={busy || credential === null}
        onClick={() => {
          if (credential === null) return;
          startTransition(async () => {
            setOutcome(
              await testSavedConnection(id, credential).catch(() => ({
                ok: false,
                message: "Sem conexão. Tente de novo.",
              })),
            );
          });
        }}
      >
        Testar
      </button>
    </BottomSheet>
  );
}
