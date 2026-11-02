"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AuthShell, FormMessage } from "@/components/auth-shell";
import { acceptInvitation } from "@/app/(app)/membros/actions";
import {
  forgetPendingInvitation,
  pendingInvitation,
  savePendingInvitation,
} from "@/lib/orgs/pending-invitation";
import { createClient } from "@/lib/supabase/client";

function readToken(): string | null {
  const fromLink = window.location.hash.slice(1);
  if (!fromLink) return pendingInvitation();
  savePendingInvitation(fromLink);
  window.history.replaceState(null, "", window.location.pathname);
  return fromLink;
}

export default function AcceptInvitationPage() {
  const [token, setToken] = useState<string | null>(null);
  const [hasSession, setHasSession] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      const { data } = await createClient().auth.getSession();
      setToken(readToken());
      setHasSession(data.session !== null);
    }
    void load();
  }, []);

  async function accept(value: string) {
    setBusy(true);
    const { accepted, error: failure } = await acceptInvitation(value).catch(() => ({
      accepted: false,
      error: "Sem conexão. Tente de novo.",
    }));
    if (accepted) {
      forgetPendingInvitation();
      setToken(null);
    }
    setError(failure);
    setBusy(false);
    if (failure === null) window.location.assign("/");
  }

  return (
    <AuthShell>
      <section className="stack">
        <h2 className="title">Convite para uma organização</h2>
        <FormMessage error={error} />
        {hasSession !== null && token === null && error === null && (
          <FormMessage error="Link de convite incompleto. Abra de novo o link do e-mail." />
        )}
        {hasSession === false && token !== null && (
          <>
            <p className="muted small">Entre com o e-mail que recebeu o convite para aceitar.</p>
            <Link className="btn primary" href="/login?next=/convites/aceitar">
              Entrar para aceitar
            </Link>
          </>
        )}
        {hasSession === true && token !== null && (
          <button
            className="btn primary"
            type="button"
            disabled={busy}
            onClick={() => void accept(token)}
          >
            Aceitar convite
          </button>
        )}
        {hasSession === true && (
          <form action="/auth/sair" method="post">
            <button className="btn" type="submit">
              Entrar com outro e-mail
            </button>
          </form>
        )}
      </section>
    </AuthShell>
  );
}
