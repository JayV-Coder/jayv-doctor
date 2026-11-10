"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import type { JiraConnection } from "@/lib/api";
import { useIdempotencyKey } from "@/lib/forms/use-idempotency-key";
import { configureJira, disconnectJira } from "./actions";

const SEVERITIES = [
  ["critical", "Crítica"],
  ["high", "Alta"],
  ["medium", "Média"],
  ["low", "Baixa"],
] as const;

export function JiraConfig({ connection }: { connection: JiraConnection }) {
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, startTransition] = useTransition();
  const [key, settle] = useIdempotencyKey();
  const [dropKey, settleDrop] = useIdempotencyKey();
  const sites = connection.sites as { id: string; name: string; url: string }[];
  const priorities = connection.priority_map;

  return (
    <form
      className="stack"
      aria-label="Configuração do Jira"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        startTransition(async () => {
          const outcome = await configureJira(form, key());
          settle(outcome);
          setError(outcome.ok ? null : outcome.message);
          setSaved(outcome.ok);
        });
      }}
    >
      <label className="field">
        Site
        <select name="site" defaultValue={connection.cloud_id ?? sites[0]?.id ?? ""} required>
          {sites.map((site) => (
            <option key={site.id} value={site.id}>
              {site.name || site.url}
            </option>
          ))}
        </select>
      </label>
      <div className="grid2">
        <label className="field">
          Projeto
          <input
            name="project"
            required
            pattern="[A-Za-z][A-Za-z0-9_]{1,19}"
            autoCapitalize="characters"
            defaultValue={connection.project_key ?? ""}
            placeholder="SUST"
          />
        </label>
        <label className="field">
          Tipo de issue
          <input
            name="issue-type"
            required
            defaultValue={connection.issue_type ?? ""}
            placeholder="Incidente"
          />
        </label>
      </div>
      <fieldset className="stack">
        <legend className="label">Severidade → prioridade do Jira</legend>
        <div className="grid2">
          {SEVERITIES.map(([value, label]) => (
            <label key={value} className="field">
              {label}
              <input name={`priority-${value}`} defaultValue={priorities[value] ?? ""} />
            </label>
          ))}
        </div>
      </fieldset>
      <label className="option">
        <input type="checkbox" role="switch" name="sync" defaultChecked={connection.sync_status} />{" "}
        Sincronizar status e comentários com #doctor
      </label>
      <p className="muted small">
        O chamado leva o resumo do Diagnóstico, a causa com confiança heurística, as Recomendações e
        o link para o Incidente. Comentários do Doctor que começam com #jira vão para o chamado.
      </p>
      <FormMessage error={error} notice={saved ? "Configuração salva." : null} />
      <div className="grid2">
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            startTransition(async () => {
              const outcome = await disconnectJira(dropKey());
              settleDrop(outcome);
              setError(outcome.ok ? null : outcome.message);
            });
          }}
        >
          Desconectar
        </button>
        <button type="submit" className="btn primary" disabled={busy}>
          Salvar
        </button>
      </div>
    </form>
  );
}
