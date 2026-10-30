"use client";

import Link from "next/link";
import { useState, type SubmitEvent } from "react";
import { FormMessage } from "@/components/auth-shell";
import { authErrorMessage } from "@/lib/auth/messages";
import { callbackUrl } from "@/lib/auth/urls";
import { createClient } from "@/lib/supabase/client";
import { SITE_URL } from "@/lib/supabase/env";

export function LoginForm({ initialError }: { initialError: string | null }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [withPassword, setWithPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initialError);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const { auth } = createClient();
    if (withPassword) {
      const result = await auth.signInWithPassword({ email, password });
      if (!result.error) {
        // Navegação completa: o proxy precisa ver os cookies novos para decidir sobre o MFA.
        window.location.assign("/");
        return;
      }
      setError(authErrorMessage(result.error));
    } else {
      const result = await auth.signInWithOtp({
        email,
        options: { emailRedirectTo: callbackUrl(SITE_URL) },
      });
      if (result.error) setError(authErrorMessage(result.error));
      else setNotice("Enviamos um link de acesso para o seu e-mail.");
    }
    setBusy(false);
  }

  async function signInWithGoogle() {
    setBusy(true);
    setError(null);
    const { error: oauthError } = await createClient().auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: callbackUrl(SITE_URL) },
    });
    if (oauthError) {
      setError(authErrorMessage(oauthError));
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={(event) => void submit(event)}>
      <label className="field">
        E-mail corporativo
        <input
          type="email"
          name="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
          }}
        />
      </label>
      {withPassword && (
        <label className="field">
          Senha
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
            }}
          />
        </label>
      )}
      <FormMessage error={error} notice={notice} />
      <button className="btn primary" type="submit" disabled={busy}>
        {withPassword ? "Entrar" : "Enviar link de acesso"}
      </button>
      <div className="divider">
        <span className="label">ou</span>
      </div>
      <button className="btn" type="button" disabled={busy} onClick={() => void signInWithGoogle()}>
        Continuar com Google
      </button>
      <button
        className="btn"
        type="button"
        onClick={() => {
          setWithPassword(!withPassword);
          setError(null);
          setNotice(null);
        }}
      >
        {withPassword ? "Entrar com link" : "Entrar com senha"}
      </button>
      {withPassword && (
        <p className="foot">
          <Link href="/esqueci-senha">Esqueci minha senha</Link>
        </p>
      )}
    </form>
  );
}
