"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { requestDiagnosis } from "../actions";

// "Novo diagnóstico" cria a versão N+1; o pedido é assíncrono e o progresso aparece no card. A
// chave fica a mesma enquanto o pedido for o mesmo (repetir depois de uma resposta perdida devolve
// o mesmo Diagnóstico) e muda junto com o modo ou a Base.
export function NewDiagnosis({ incidentId }: { incidentId: string }) {
  const router = useRouter();
  const [mode, setMode] = useState<"hybrid" | "rules_only">("hybrid");
  const [knowledge, setKnowledge] = useState(true);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();

  return (
    <BottomSheet
      title="Novo diagnóstico"
      trigger="Novo diagnóstico"
      onClose={() => {
        // Fechar depois de um erro recomeça o pedido com chave nova.
        if (error !== null) setKey(crypto.randomUUID());
        setError(null);
      }}
    >
      <fieldset className="choice">
        <legend>Modo</legend>
        <label className="option">
          <input
            type="radio"
            name="mode"
            checked={mode === "hybrid"}
            onChange={() => {
              setMode("hybrid");
              setKey(crypto.randomUUID());
            }}
          />
          Híbrido: Regras, Base de conhecimento e IA
        </label>
        <label className="option">
          <input
            type="radio"
            name="mode"
            checked={mode === "rules_only"}
            onChange={() => {
              setMode("rules_only");
              setKey(crypto.randomUUID());
            }}
          />
          Só Regras (sem IA)
        </label>
        <label className="option">
          <input
            type="checkbox"
            checked={knowledge}
            disabled={mode === "rules_only"}
            onChange={(event) => {
              setKnowledge(event.currentTarget.checked);
              setKey(crypto.randomUUID());
            }}
          />
          Consultar a Base de conhecimento
        </label>
      </fieldset>
      <FormMessage error={error} />
      <button
        type="button"
        className="btn primary"
        disabled={busy}
        onClick={(event) => {
          const dialog = event.currentTarget.closest("dialog");
          startTransition(async () => {
            const failure = await requestDiagnosis(
              incidentId,
              { mode, include_knowledge_base: mode === "hybrid" && knowledge },
              key,
            ).catch(() => "Sem conexão. Tente de novo.");
            setError(failure);
            if (failure === null) {
              setKey(crypto.randomUUID());
              dialog?.close();
              router.push(`/incidentes/${incidentId}`);
              router.refresh();
            }
          });
        }}
      >
        Diagnosticar
      </button>
    </BottomSheet>
  );
}
