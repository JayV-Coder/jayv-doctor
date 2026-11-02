"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { renewSession } from "@/app/(app)/membros/actions";

// O JWT leva até 1 h para trazer um Papel novo; quem acabou de ser promovido não precisa esperar.
export function RenewSessionButton() {
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();

  return (
    <>
      <FormMessage error={error} />
      <button
        type="button"
        className="btn"
        disabled={busy}
        onClick={() => {
          startTransition(async () => {
            const failure = await renewSession().catch(() => "Sem conexão. Tente de novo.");
            setError(failure);
            if (failure === null) window.location.reload();
          });
        }}
      >
        Atualizar meu acesso
      </button>
    </>
  );
}
