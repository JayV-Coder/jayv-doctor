import type { ReactNode } from "react";

// O tom vai no ponto, e o texto diz o mesmo: a cor nunca é a única pista.
export type ChipTone = "success" | "danger" | "warning" | "info" | "neutral";

export function Chip({ tone = "neutral", children }: { tone?: ChipTone; children: ReactNode }) {
  return (
    <span className="chip" data-tone={tone === "success" ? undefined : tone}>
      {children}
    </span>
  );
}
