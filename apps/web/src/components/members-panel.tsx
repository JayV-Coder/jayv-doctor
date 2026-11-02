"use client";

import { useState, useTransition, type SubmitEvent } from "react";
import { FormMessage, Win } from "@/components/auth-shell";
import {
  changeRole,
  invite,
  removeMember,
  resendInvitation,
  revokeInvitation,
} from "@/app/(app)/membros/actions";
import type { Invitation, Member } from "@/lib/api";
import { initials, roleLabel } from "@/lib/orgs/labels";
import { matchesSearch } from "@/lib/orgs/slug";

const INVITE_ROLES = [
  { value: "analyst", label: "Analyst — investiga e revisa diagnósticos" },
  { value: "viewer", label: "Viewer — somente leitura" },
  { value: "admin", label: "Admin — gerencia conectores e membros" },
];

const OWNER_ROLE = { value: "owner", label: "Owner — controle total" };

function daysLeft(expiresAt: string): number {
  return Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 86_400_000);
}

export function MembersPanel({
  members,
  invitations,
  viewerRole,
}: {
  members: Member[];
  invitations: Invitation[];
  viewerRole: string;
}) {
  const [query, setQuery] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("analyst");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const isOwner = viewerRole === "owner";
  const roles = isOwner ? [...INVITE_ROLES, OWNER_ROLE] : INVITE_ROLES;
  const visible = members.filter((member) =>
    matchesSearch(`${member.display_name ?? ""} ${member.email}`, query),
  );

  function run(action: () => Promise<string | null>, success?: string) {
    startTransition(async () => {
      const failure = await action().catch(() => "Sem conexão. Tente de novo.");
      setError(failure);
      setNotice(failure === null ? (success ?? null) : null);
    });
  }

  function submit(event: SubmitEvent) {
    event.preventDefault();
    run(() => invite(email, role), `Convite enviado para ${email}.`);
    setEmail("");
  }

  return (
    <div className="stack">
      <label className="field">
        Buscar por nome ou e-mail
        <input
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
        />
      </label>
      <FormMessage error={error} notice={notice} />
      <ul className="org-list">
        {visible.map((member) => {
          const name = member.display_name ?? member.email;
          const locked = member.role === "owner" && !isOwner;
          return (
            <li key={member.id} className="member">
              <div className="member-head">
                <span className="avatar" aria-hidden="true">
                  {initials(name)}
                </span>
                <span className="org-name">
                  <strong>{name}</strong>
                  <span className="muted small">
                    {member.email}
                    {member.mfa_enabled ? " · MFA ativo" : ""}
                  </span>
                </span>
              </div>
              {locked ? (
                <span className="tag">{roleLabel(member.role)}</span>
              ) : (
                <div className="member-actions">
                  <label className="field">
                    Papel de {name}
                    <select
                      value={member.role}
                      disabled={busy}
                      onChange={(event) => {
                        const next = event.target.value;
                        run(() => changeRole(member.id, next));
                      }}
                    >
                      {roles.map((option) => (
                        <option key={option.value} value={option.value}>
                          {roleLabel(option.value)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    className="btn"
                    disabled={busy}
                    aria-label={`Remover ${name}`}
                    onClick={() => {
                      run(() => removeMember(member.id));
                    }}
                  >
                    Remover
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {invitations.length > 0 && (
        <>
          <p className="label">Convites pendentes</p>
          <ul className="org-list">
            {invitations.map((invitation) => (
              <li key={invitation.id} className="member">
                <div className="member-head">
                  <span className="avatar" aria-hidden="true">
                    ?
                  </span>
                  <span className="org-name">
                    <strong>{invitation.email}</strong>
                    <span className="muted small">
                      {roleLabel(invitation.role)} ·{" "}
                      {daysLeft(invitation.expires_at) > 0
                        ? `expira em ${String(daysLeft(invitation.expires_at))} dias`
                        : "expirado"}
                    </span>
                  </span>
                </div>
                <div className="member-actions">
                  <button
                    type="button"
                    className="btn"
                    disabled={busy}
                    onClick={() => {
                      run(
                        () => resendInvitation(invitation.id),
                        `Convite reenviado para ${invitation.email}.`,
                      );
                    }}
                  >
                    Reenviar
                  </button>
                  <button
                    type="button"
                    className="btn"
                    disabled={busy}
                    onClick={() => {
                      run(() => revokeInvitation(invitation.id));
                    }}
                  >
                    Revogar
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      <Win title="novo convite">
        <form className="stack" onSubmit={submit}>
          <label className="field">
            E-mail
            <input
              type="email"
              required
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
              }}
            />
          </label>
          <label className="field">
            Papel do convidado
            <select
              value={role}
              onChange={(event) => {
                setRole(event.target.value);
              }}
            >
              {roles.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button className="btn primary" type="submit" disabled={busy}>
            Enviar convite
          </button>
        </form>
      </Win>
    </div>
  );
}
