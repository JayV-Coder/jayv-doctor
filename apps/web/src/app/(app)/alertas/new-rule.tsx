"use client";

import { useRef, useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { createRule } from "./actions";
import { useIdempotencyKey } from "@/lib/forms/use-idempotency-key";

const TYPES = [
  { value: "incident", label: "Incidente aberto ou atualizado" },
  { value: "error_rate", label: "Taxa de erro acima do limite" },
  { value: "connector_failing", label: "Conector com falhas" },
  { value: "diagnosis_review", label: "Diagnóstico aguardando revisão" },
];

export function NewRule({ channels }: { channels: { id: string; name: string }[] }) {
  const [type, setType] = useState("incident");
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const [key, settle] = useIdempotencyKey();
  const formRef = useRef<HTMLFormElement>(null);

  return (
    <BottomSheet
      title="Nova regra"
      trigger="Nova regra"
      triggerClassName="btn primary"
      onClose={() => {
        setError(null);
      }}
    >
      <form
        ref={formRef}
        className="stack"
        onSubmit={(event) => {
          // `onSubmit`, não `action`: o `action` limpa o formulário, e depois de um erro a
          // pessoa perderia o que digitou.
          event.preventDefault();
          const element = event.currentTarget;
          const form = new FormData(element);
          startTransition(async () => {
            const outcome = await createRule(form, key());
            settle(outcome);
            setError(outcome.ok ? null : outcome.message);
            if (outcome.ok) {
              // Sem o reset do `action`: limpa à mão (o webhook não fica no formulário).
              element.reset();
              formRef.current?.closest("dialog")?.close();
            }
          });
        }}
      >
        <label className="field">
          Nome
          <input name="name" required minLength={2} maxLength={80} placeholder="Crítico em prd" />
        </label>
        <label className="field">
          Quando
          <select
            name="type"
            value={type}
            onChange={(event) => {
              setType(event.currentTarget.value);
            }}
          >
            {TYPES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        {type === "incident" && (
          <>
            <label className="field">
              Severidade mínima
              <select name="severity" defaultValue="critical">
                <option value="critical">Crítica</option>
                <option value="high">Alta</option>
                <option value="medium">Média</option>
                <option value="low">Baixa</option>
              </select>
            </label>
            <fieldset className="stack">
              <legend className="label">Ambientes (nenhum marcado = todos)</legend>
              {[
                ["prd", "Produção"],
                ["hml", "Homologação"],
                ["dev", "Desenvolvimento"],
              ].map(([value, label]) => (
                <label key={value} className="option">
                  <input type="checkbox" name="environment" value={value} /> {label}
                </label>
              ))}
            </fieldset>
          </>
        )}
        {type === "error_rate" && (
          <>
            <label className="field">
              Limite de erro (%)
              <input name="threshold" type="number" min={1} max={100} defaultValue={5} />
            </label>
            <label className="field">
              Janela (minutos)
              <input name="minutes" type="number" min={5} max={1440} defaultValue={10} />
            </label>
          </>
        )}
        {type === "diagnosis_review" && (
          <label className="field">
            Sem revisão há (minutos)
            <input name="minutes" type="number" min={5} max={1440} defaultValue={30} />
          </label>
        )}
        <fieldset className="stack">
          <legend className="label">Enviar para</legend>
          {channels.length === 0 && <p className="muted small">Cadastre um canal antes.</p>}
          {channels.map((channel) => (
            <label key={channel.id} className="option">
              <input type="checkbox" name="channel" value={channel.id} /> {channel.name}
            </label>
          ))}
        </fieldset>
        <fieldset className="stack">
          <legend className="label">Silêncio da regra (opcional, exceto crítico)</legend>
          <label className="field">
            Das
            <input name="quiet-start" type="time" />
          </label>
          <label className="field">
            Até
            <input name="quiet-end" type="time" />
          </label>
        </fieldset>
        <FormMessage error={error} />
        <button type="submit" className="btn primary" disabled={busy}>
          Salvar regra
        </button>
      </form>
    </BottomSheet>
  );
}
