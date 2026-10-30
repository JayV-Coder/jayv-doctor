"use client";

import Link from "next/link";
import { useRef, useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { switchOrganization } from "@/app/organizacoes/actions";
import type { Organization } from "@/lib/api";

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  analyst: "Analyst",
  viewer: "Viewer",
};

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join("");
}

export function OrgList({
  organizations,
  activeId,
}: {
  organizations: Organization[];
  activeId: string | null;
}) {
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const visible = organizations.filter((organization) =>
    organization.name.toLowerCase().includes(query.trim().toLowerCase()),
  );

  function choose(id: string) {
    startTransition(async () => {
      const failure = await switchOrganization(id);
      setError(failure);
      if (failure === null) window.location.assign("/");
    });
  }

  return (
    <div className="stack">
      <label className="field">
        Buscar organização
        <input
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
        />
      </label>
      <ul className="org-list">
        {visible.map((organization) => (
          <li key={organization.id}>
            <button
              type="button"
              className="org-item"
              disabled={busy}
              aria-current={organization.id === activeId}
              onClick={() => {
                if (organization.id !== activeId) choose(organization.id);
              }}
            >
              <span className="avatar" aria-hidden="true">
                {initials(organization.name)}
              </span>
              <span className="org-name">
                <strong>{organization.name}</strong>
                <span className="muted small">
                  {ROLE_LABELS[organization.role] ?? organization.role}
                </span>
              </span>
              {organization.id === activeId && <span className="tag">Ativa</span>}
            </button>
          </li>
        ))}
      </ul>
      <FormMessage error={error} />
      <Link className="btn" href="/organizacoes/nova">
        + Criar nova organização
      </Link>
    </div>
  );
}

export function OrgSwitcher({
  organizations,
  active,
}: {
  organizations: Organization[];
  active: Organization;
}) {
  const dialog = useRef<HTMLDialogElement>(null);

  return (
    <>
      <div className="org-top">
        <h2 className="title">{active.name}</h2>
        <button
          type="button"
          className="btn"
          aria-label={`Trocar de organização: ${active.name}`}
          onClick={() => dialog.current?.showModal()}
        >
          Trocar ▾
        </button>
      </div>
      <dialog ref={dialog} className="sheet" aria-label="Trocar de organização">
        <div className="stack">
          <p className="title">Trocar de organização</p>
          <p className="muted small">
            Ao trocar, sua sessão é renovada e você vê apenas os dados da organização escolhida.
          </p>
          <OrgList organizations={organizations} activeId={active.id} />
          <button type="button" className="btn" onClick={() => dialog.current?.close()}>
            Fechar
          </button>
        </div>
      </dialog>
    </>
  );
}
