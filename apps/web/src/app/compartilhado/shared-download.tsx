"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";

function filename(disposition: string | null): string {
  return /filename="([^"]+)"/.exec(disposition ?? "")?.[1] ?? "relatorio";
}

export function SharedDownload() {
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  return (
    <>
      <FormMessage error={error} />
      <button
        type="button"
        className="btn primary"
        disabled={busy}
        onClick={() => {
          setError(null);
          startTransition(async () => {
            const token = window.location.hash.slice(1);
            const response = await fetch("/compartilhado/arquivo", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ token }),
            }).catch(() => null);
            if (!response?.ok) {
              setError(
                response?.status === 404
                  ? "Link inválido, vencido ou revogado."
                  : "Não foi possível baixar agora. Tente de novo.",
              );
              return;
            }
            const url = URL.createObjectURL(await response.blob());
            const anchor = document.createElement("a");
            anchor.href = url;
            anchor.download = filename(response.headers.get("content-disposition"));
            anchor.click();
            URL.revokeObjectURL(url);
          });
        }}
      >
        Baixar relatório
      </button>
    </>
  );
}
