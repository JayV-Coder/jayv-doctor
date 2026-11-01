"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AuthShell, FormMessage } from "@/components/auth-shell";
import { acceptInvitation } from "@/app/membros/actions";
import { createClient } from "@/lib/supabase/client";

const PENDING_TOKEN = "convite-pendente";

// O login não preserva o fragmento: o token espera na aba e some depois do aceite.
function readToken(): string | null {
  const fromLink = window.location.hash.slice(1);
  try {
    if (fromLink) {
      window.sessionStorage.setItem(PENDING_TOKEN, fromLink);
      window.history.replaceState(null, "", window.location.pathname);
    }
    return fromLink || window.sessionStorage.getItem(PENDING_TOKEN);
  } catch {
    return fromLink || null;
  }
}

function forgetToken() {
  try {
    window.sessionStorage.removeItem(PENDING_TOKEN);
  } catch {
    return;
  }
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
    const failure = await acceptInvitation(value).catch(() => "Sem conexão. Tente de novo.");
    setError(failure);
    if (failure === null) {
      forgetToken();
      window.location.assign("/");
    } else {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      <section className="stack">
        <h2 className="title">Convite para uma organização</h2>
        <FormMessage error={error} />
        {hasSession !== null && token === null && (
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
      </section>
    </AuthShell>
  );
}
