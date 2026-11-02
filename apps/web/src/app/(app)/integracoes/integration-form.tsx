"use client";

import { useEffect, useRef, useState, type SubmitEvent } from "react";
import { FormMessage } from "@/components/auth-shell";
import { ENVIRONMENTS, SYSTEMS } from "@/lib/integrations/labels";
import { createIntegration } from "./actions";

export function IntegrationForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  // A folha que contém o formulário vem do servidor: o fechamento é ouvido aqui, para a próxima
  // abertura começar limpa, sem o erro da tentativa anterior.
  useEffect(() => {
    const form = formRef.current;
    const dialog = form?.closest("dialog");
    function clear() {
      setError(null);
      form?.reset();
    }
    dialog?.addEventListener("close", clear);
    return () => dialog?.removeEventListener("close", clear);
  }, []);

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    const failure = await createIntegration(new FormData(form)).catch(
      () => "Sem conexão. Tente de novo.",
    );
    setBusy(false);
    setError(failure);
    if (failure === null) form.closest("dialog")?.close();
  }

  return (
    <form ref={formRef} className="stack" onSubmit={(event) => void submit(event)}>
      <label className="field">
        Nome
        <input name="name" required minLength={2} maxLength={80} />
      </label>
      <div className="grid2">
        <label className="field">
          Origem
          <select name="source_system" required defaultValue="">
            <option value="" disabled>
              Selecione
            </option>
            {SYSTEMS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Destino
          <select name="target_system" required defaultValue="">
            <option value="" disabled>
              Selecione
            </option>
            {SYSTEMS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="field">
        Ambiente
        <select name="environment" required defaultValue="prd">
          {ENVIRONMENTS.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        Time responsável (opcional)
        <input name="owner_team" maxLength={80} />
      </label>
      <label className="field">
        Descrição (opcional)
        <textarea name="description" maxLength={500} rows={3} />
      </label>
      <FormMessage error={error} />
      <button className="btn primary" type="submit" disabled={busy}>
        Salvar integração
      </button>
    </form>
  );
}
