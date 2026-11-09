"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { shareExpiry } from "@/lib/reports/labels";
import { revokeShare } from "./actions";

type Share = { id: string; expires_at: string; access_count: number };

// Links ativos de um relatório: revogar corta o acesso na hora (ADR-0014).
export function ShareList({
  incidentId,
  reportId,
  shares,
}: {
  incidentId: string;
  reportId: string;
  shares: Share[];
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  return (
    <>
      {shares.map((share) => (
        <span key={share.id} className="row-between small">
          <span>
            Link {shareExpiry(share.expires_at)} · {share.access_count} acesso(s)
          </span>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => {
              startTransition(async () => {
                setError(await revokeShare(incidentId, reportId, share.id));
              });
            }}
          >
            Revogar
          </button>
        </span>
      ))}
      <FormMessage error={error} />
    </>
  );
}
