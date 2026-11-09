"use client";

import { useState, useTransition } from "react";
import type { RegistrationToken } from "@/lib/api";
import { revokeAgent, rotateAgent } from "./actions";
import { InstallCommand } from "./install-command";

export function AgentActions({
  id,
  name,
  revoked,
}: {
  id: string;
  name: string;
  revoked: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<RegistrationToken | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, startTransition] = useTransition();
  if (revoked) return null;

  return (
    <>
      <div className="grid2">
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            startTransition(async () => {
              const issued = await rotateAgent(id);
              setError(issued.ok ? null : issued.message);
              setToken(issued.ok ? issued.token : null);
            });
          }}
        >
          Novo token
        </button>
        <button
          type="button"
          className={confirming ? "btn primary" : "btn"}
          disabled={busy}
          aria-label={confirming ? `Confirmar revogação de ${name}` : `Revogar ${name}`}
          onClick={() => {
            if (!confirming) {
              setConfirming(true);
              return;
            }
            startTransition(async () => {
              setError(await revokeAgent(id));
              setConfirming(false);
            });
          }}
        >
          {confirming ? "Confirmar" : "Revogar"}
        </button>
      </div>
      {confirming && (
        <p className="alert notice action-message" role="status">
          O agente para na próxima chamada e precisa ser instalado de novo para voltar.
        </p>
      )}
      {error && (
        <p className="alert action-message" role="alert">
          {error}
        </p>
      )}
      {token && <InstallCommand token={token} />}
    </>
  );
}
