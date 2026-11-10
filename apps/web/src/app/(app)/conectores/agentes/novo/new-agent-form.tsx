"use client";

import Link from "next/link";
import { useRef, useState, useTransition } from "react";
import type { RegistrationToken } from "@/lib/api";
import { createAgent } from "../actions";
import { InstallCommand } from "../install-command";

type Option = { id: string; name: string; environment: string };

export function NewAgentForm({ integrations }: { integrations: Option[] }) {
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<RegistrationToken | null>(null);
  const [busy, startTransition] = useTransition();
  const key = useRef(crypto.randomUUID());

  if (token) {
    return (
      <div className="stack">
        <InstallCommand token={token} />
        <Link className="btn primary" href="/conectores/agentes">
          Ver agentes
        </Link>
      </div>
    );
  }
  return (
    <form
      className="stack"
      action={(form) => {
        startTransition(async () => {
          const issued = await createAgent(form, key.current);
          if (!issued.ok && !issued.offline) key.current = crypto.randomUUID();
          setError(issued.ok ? null : issued.message);
          if (issued.ok) setToken(issued.token);
        });
      }}
    >
      <label className="field">
        Nome do agente
        <input name="name" required minLength={2} maxLength={80} placeholder="SAP ECC Campinas" />
      </label>
      <label className="field">
        Integração
        <select name="integration_id" required>
          {integrations.map(({ id, name, environment }) => (
            <option key={id} value={id}>
              {name} ({environment})
            </option>
          ))}
        </select>
      </label>
      <h2 className="label">O que o agente pode coletar</h2>
      <label className="field">
        Pasta de exportações (SM58, SLG1, IDocs)
        <input
          name="directory"
          placeholder="/exports/sap"
          pattern="/.*"
          autoCapitalize="none"
          spellCheck={false}
        />
      </label>
      <label className="field">
        Arquivos
        <input name="pattern" defaultValue="*.csv" autoCapitalize="none" spellCheck={false} />
      </label>
      <label className="option">
        <input type="checkbox" name="idoc" /> Status de IDoc via RFC (tabela EDIDS)
      </label>
      <label className="field">
        Função de leitura customizada (opcional)
        <input
          name="function"
          placeholder="Z_AID_READ_SLG1"
          pattern="Z_AID_[A-Z0-9_]{1,24}"
          autoCapitalize="characters"
          spellCheck={false}
        />
      </label>
      <p className="muted small">
        Só o que está marcado aqui é coletado. RFC usa um usuário técnico só de leitura, configurado
        na máquina do agente.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      <div className="grid2">
        <Link className="btn" href="/conectores/agentes">
          Cancelar
        </Link>
        <button type="submit" className="btn primary" disabled={busy}>
          Gerar token
        </button>
      </div>
    </form>
  );
}
