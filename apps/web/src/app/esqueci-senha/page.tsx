"use client";

import Link from "next/link";
import { useState, type SubmitEvent } from "react";
import { AuthShell, FormMessage } from "@/components/auth-shell";
import { authErrorMessage } from "@/lib/auth/messages";
import { createClient } from "@/lib/supabase/client";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const result = await createClient().auth.resetPasswordForEmail(email);
    if (result.error) setError(authErrorMessage(result.error));
    // A mesma resposta exista ou não a conta: a tela não revela quem é cliente.
    else setNotice("Se houver uma conta com esse e-mail, enviamos um link para redefinir a senha.");
    setBusy(false);
  }

  return (
    <AuthShell>
      <form className="stack" onSubmit={(event) => void submit(event)}>
        <label className="field">
          E-mail corporativo
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
            }}
          />
        </label>
        <FormMessage error={error} notice={notice} />
        <button className="btn primary" type="submit" disabled={busy}>
          Enviar link de redefinição
        </button>
        <Link className="btn" href="/login">
          Voltar para o login
        </Link>
      </form>
    </AuthShell>
  );
}
