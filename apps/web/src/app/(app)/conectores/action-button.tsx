"use client";

import { useEffect, useState, useTransition } from "react";
import { runConnectorAction } from "./actions";

const LABELS = { sync: "Sincronizar", pause: "Pausar", resume: "Retomar" } as const;

export function ActionButton({
  id,
  action,
  primary = false,
}: {
  id: string;
  action: keyof typeof LABELS;
  primary?: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, startTransition] = useTransition();

  // O aviso de pedido feito some sozinho; o status de verdade chega pelo card.
  useEffect(() => {
    if (!done) return;
    const timer = setTimeout(() => {
      setDone(false);
    }, 6000);
    return () => {
      clearTimeout(timer);
    };
  }, [done]);

  return (
    <>
      <button
        type="button"
        className={primary ? "btn primary" : "btn"}
        disabled={busy}
        onClick={() => {
          startTransition(async () => {
            const failure = await runConnectorAction(id, action).catch(
              () => "Sem conexão. Tente de novo.",
            );
            setError(failure);
            setDone(failure === null && action === "sync");
          });
        }}
      >
        {LABELS[action]}
      </button>
      {error && (
        <p className="alert action-message" role="alert">
          {error}
        </p>
      )}
      {done && (
        <p className="alert notice action-message" role="status">
          Sincronização pedida. O status atualiza quando ela terminar.
        </p>
      )}
    </>
  );
}
