"use client";

import { useRef } from "react";

// Chave idempotente por intenção: repete-se quando não houve resposta (rede caiu, clique
// duplo); com resposta da API, a próxima tentativa usa outra.
export function useIdempotencyKey(): [
  () => string,
  (outcome: { ok: boolean; offline?: boolean }) => void,
] {
  const key = useRef(crypto.randomUUID());
  return [
    () => key.current,
    (outcome) => {
      if (outcome.ok || !outcome.offline) key.current = crypto.randomUUID();
    },
  ];
}
