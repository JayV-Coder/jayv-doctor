"use client";

import { useRef, useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { SYSTEMS } from "@/lib/correlation/form";
import { createMapping } from "./actions";

type Option = { id: string; name: string; provider: string };

// Linhas na ordem do fluxo: origem, middleware, destino.
function defaults(source: string, target: string): string[] {
  return [source, "gcp", target].map((system) => (system === "other" ? "custom" : system));
}

export function MappingForm({
  integration,
  source,
  target,
  connectors,
}: {
  integration: string;
  source: string;
  target: string;
  connectors: Option[];
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const key = useRef(crypto.randomUUID());
  const formRef = useRef<HTMLFormElement>(null);
  const systems = defaults(source, target);

  return (
    <BottomSheet
      title="Novo mapa"
      trigger="Novo mapa"
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
          const form = new FormData(event.currentTarget);
          startTransition(async () => {
            const outcome = await createMapping(integration, form, key.current);
            if (outcome.ok || !outcome.offline) key.current = crypto.randomUUID();
            setError(outcome.ok ? null : outcome.message);
            if (outcome.ok) formRef.current?.closest("dialog")?.close();
          });
        }}
      >
        <label className="field">
          Nome
          <input name="name" required minLength={2} maxLength={80} placeholder="Pedido de venda" />
        </label>
        <p className="muted small">
          Onde cada sistema guarda a mesma chave. Os Eventos com a chave igual entram na mesma
          Execução.
        </p>
        {systems.map((system, row) => (
          <fieldset key={row} className="stack">
            <legend className="label">Chave {row + 1}</legend>
            <label className="field">
              Sistema
              <select name={`system-${String(row)}`} defaultValue={system}>
                {SYSTEMS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Campo do Evento
              <input
                name={`field-${String(row)}`}
                placeholder="execution_id ou attributes.bstkd"
                autoCapitalize="none"
                spellCheck={false}
              />
            </label>
            <label className="field">
              Tirar o prefixo
              <input name={`prefix-${String(row)}`} maxLength={32} placeholder="SF-" />
            </label>
            <label className="option">
              <input type="checkbox" name={`zeros-${String(row)}`} /> Tirar zeros à esquerda
            </label>
            <label className="option">
              <input type="checkbox" name={`upper-${String(row)}`} /> Comparar em maiúsculas
            </label>
          </fieldset>
        ))}
        <label className="field">
          Janela (minutos)
          <input name="window" type="number" min={1} max={1440} defaultValue={60} />
        </label>
        <label className="option">
          <input type="checkbox" name="reconcile" /> Avisar quando a origem não chegar ao destino
          (INT-008)
        </label>
        <fieldset className="stack">
          <legend className="label">Consulta no destino (opcional)</legend>
          <label className="field">
            Conector
            <select name="connector" defaultValue="">
              <option value="">Sem consulta</option>
              {connectors.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Entidade ou objeto
            <input
              name="entity"
              placeholder="A_SalesOrder"
              autoCapitalize="none"
              spellCheck={false}
            />
          </label>
          <label className="field">
            Campo da chave
            <input
              name="lookup-field"
              placeholder="PurchaseOrderByCustomer"
              autoCapitalize="none"
              spellCheck={false}
            />
          </label>
          <label className="field">
            Campo de status (opcional)
            <input name="status-field" autoCapitalize="none" spellCheck={false} />
          </label>
          <label className="field">
            Campo com o nº do registro (opcional)
            <input
              name="id-field"
              placeholder="SalesOrder"
              autoCapitalize="none"
              spellCheck={false}
            />
          </label>
          <label className="field">
            Completar com zeros até
            <input name="pad" type="number" min={0} max={35} defaultValue={0} />
          </label>
        </fieldset>
        <FormMessage error={error} />
        <button type="submit" className="btn primary" disabled={busy}>
          Salvar mapa
        </button>
      </form>
    </BottomSheet>
  );
}
