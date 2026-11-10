"use client";

import { useRef, useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import type { ServiceNowConnection } from "@/lib/api";
import { useIdempotencyKey } from "@/lib/forms/use-idempotency-key";
import { CopyCommand } from "../conectores/novo/copy-command";
import { configureServiceNow, disconnectServiceNow } from "./actions";

const SYSTEMS = [
  ["sap", "SAP"],
  ["salesforce", "Salesforce"],
  ["gcp", "GCP"],
  ["other", "Outro"],
] as const;

// ServiceNow (#44): instância, app OAuth (client credentials) e o grupo por Sistema responsável.
// O secret vai para o Vault e não volta; o endereço da Business Rule aparece uma vez.
export function ServiceNowConfig({ connection }: { connection: ServiceNowConnection | null }) {
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [hookUrl, setHookUrl] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const [key, settle] = useIdempotencyKey();
  const [dropKey, settleDrop] = useIdempotencyKey();
  const formRef = useRef<HTMLFormElement>(null);
  const groups = connection?.assignment_groups ?? {};

  return (
    <form
      ref={formRef}
      className="stack"
      aria-label="Configuração do ServiceNow"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        startTransition(async () => {
          const outcome = await configureServiceNow(form, key());
          settle(outcome);
          setError(outcome.ok ? null : outcome.message);
          setSaved(outcome.ok);
          if (outcome.ok) {
            setHookUrl(outcome.value.hook_url ?? null);
            const secret = formRef.current?.elements.namedItem("client-secret");
            if (secret instanceof HTMLInputElement) secret.value = "";
          }
        });
      }}
    >
      <label className="field">
        Instância
        <input
          name="instance"
          type="url"
          required
          autoCapitalize="none"
          spellCheck={false}
          pattern="https://[a-z0-9][a-z0-9\-]{0,62}\.service-now\.com/?"
          defaultValue={connection?.instance_url ?? ""}
          placeholder="https://empresa.service-now.com"
        />
      </label>
      <div className="grid2">
        <label className="field">
          Client ID
          <input
            name="client-id"
            required
            autoCapitalize="none"
            spellCheck={false}
            defaultValue={connection?.client_id ?? ""}
          />
        </label>
        <label className="field">
          Client secret
          <input
            name="client-secret"
            type="password"
            autoComplete="off"
            required={!connection}
            placeholder={connection ? "mantido" : ""}
          />
        </label>
      </div>
      <fieldset className="stack">
        <legend className="label">Sistema responsável → grupo de atendimento</legend>
        <div className="grid2">
          {SYSTEMS.map(([value, label]) => (
            <label key={value} className="field">
              {label}
              <input name={`group-${value}`} defaultValue={groups[value] ?? ""} />
            </label>
          ))}
        </div>
        <label className="field">
          Grupo padrão (Indeterminado)
          <input
            name="default-group"
            defaultValue={connection?.default_group ?? ""}
            placeholder="Service Desk"
          />
        </label>
      </fieldset>
      <label className="option">
        <input
          type="checkbox"
          role="switch"
          name="sync"
          defaultChecked={connection?.sync_status ?? true}
        />{" "}
        Receber o status pela Business Rule
      </label>
      {connection && (
        <label className="option">
          <input type="checkbox" name="rotate" /> Gerar outro endereço para a Business Rule
        </label>
      )}
      <p className="muted small">
        O incident leva impact e urgency pela severidade e, nas work notes, o resumo do Diagnóstico
        com a confiança heurística e o link. O grupo sai do Sistema responsável do Diagnóstico.
      </p>
      {hookUrl && (
        <div className="stack" role="status">
          <p className="alert notice">
            Guarde o endereço agora: ele não aparece de novo. A Business Rule do incident envia{" "}
            {'{"number": current.number}'} para ele (docs/operations/itsm.md).
          </p>
          <CopyCommand command={hookUrl} />
        </div>
      )}
      <FormMessage error={error} notice={saved && !hookUrl ? "Configuração salva." : null} />
      <div className="grid2">
        {connection && (
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => {
              startTransition(async () => {
                const outcome = await disconnectServiceNow(dropKey());
                settleDrop(outcome);
                setError(outcome.ok ? null : outcome.message);
              });
            }}
          >
            Desconectar
          </button>
        )}
        <button type="submit" className="btn primary" disabled={busy}>
          {connection ? "Salvar" : "Conectar ServiceNow"}
        </button>
      </div>
    </form>
  );
}
