"use client";

import { useRef } from "react";
import type { Outcome } from "./actions";

// Chave idempotente por intenção: repete-se sem resposta; com resposta, a próxima é nova.
export function useIdempotencyKey(): [() => string, (outcome: Outcome) => void] {
  const key = useRef(crypto.randomUUID());
  return [
    () => key.current,
    (outcome) => {
      if (outcome.ok || !outcome.offline) key.current = crypto.randomUUID();
    },
  ];
}
