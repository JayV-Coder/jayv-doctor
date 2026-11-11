"use client";

import Link from "next/link";
import { useState, type SubmitEvent } from "react";
import { FormMessage } from "@/components/auth-shell";
import { authErrorMessage } from "@/lib/auth/messages";
import { PASSWORD_RULES, passwordOk, passwordRules } from "@/lib/auth/password";
import { callbackUrl } from "@/lib/auth/urls";
import { createClient } from "@/lib/supabase/client";
import { SITE_URL } from "@/lib/supabase/env";

type Mode = "signIn" | "signUp";

// Entrar com e-mail e senha (ou criar a conta), Google ou link de acesso por e-mail, no mesmo
// desenho do login do jayv-coder.
export function LoginForm({ initialError, next }: { initialError: string | null; next: string }) {
  const [mode, setMode] = useState<Mode>("signIn");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initialError);
  const [notice, setNotice] = useState<string | null>(null);

  const signUp = mode === "signUp";
  const mismatch = signUp && confirm.length > 0 && confirm !== password;
  const ready = !signUp || (passwordOk(password) && confirm === password && name.trim() !== "");
  const rules = passwordRules(password);

  function switchTo(next: Mode) {
    setMode(next);
    setError(null);
    setNotice(null);
    setConfirm("");
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const { auth } = createClient();
    if (signUp) {
      const result = await auth.signUp({
        email: email.trim(),
        password,
        options: {
          emailRedirectTo: callbackUrl(SITE_URL, next),
          data: { display_name: name.trim() },
        },
      });
      if (result.error) setError(authErrorMessage(result.error));
      else if (result.data.session) {
        // Projeto sem confirmação de e-mail: a conta já entra.
        window.location.assign(next);
        return;
      } else {
        switchTo("signIn");
        setNotice("Confira seu e-mail para confirmar a conta e depois entre.");
      }
      setBusy(false);
      return;
    }
    const result = await auth.signInWithPassword({ email: email.trim(), password });
    if (!result.error) {
      // Navegação completa: o proxy precisa ver os cookies novos para decidir sobre o MFA.
      window.location.assign(next);
      return;
    }
    setError(authErrorMessage(result.error));
    setBusy(false);
  }

  async function sendLink() {
    if (!email.trim()) {
      setError("Informe o e-mail para receber o link de acesso.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    const result = await createClient().auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: callbackUrl(SITE_URL, next) },
    });
    if (result.error) setError(authErrorMessage(result.error));
    else setNotice("Enviamos um link de acesso para o seu e-mail.");
    setBusy(false);
  }

  async function signInWithGoogle() {
    setBusy(true);
    setError(null);
    const { error: oauthError } = await createClient().auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: callbackUrl(SITE_URL, next) },
    });
    if (oauthError) {
      setError(authErrorMessage(oauthError));
      setBusy(false);
    }
  }

  return (
    <>
      <form className="auth-form" onSubmit={(event) => void submit(event)}>
        <label className="auth-field">
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
        {signUp && (
          <label className="auth-field">
            Nome
            <input
              name="name"
              autoComplete="name"
              required
              maxLength={80}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </label>
        )}
        <label className="auth-field">
          Senha
          <input
            type="password"
            name="password"
            autoComplete={signUp ? "new-password" : "current-password"}
            required
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
            }}
          />
        </label>
        {signUp && (
          <>
            <ul className="auth-rules" aria-label="Regras da senha">
              {PASSWORD_RULES.map(({ rule, label }) => (
                <li key={rule} className={rules[rule] ? "ok" : undefined}>
                  <span aria-hidden="true">{rules[rule] ? "✓" : "·"}</span> {label}
                  <span className="sr-only">{rules[rule] ? " (cumprida)" : " (pendente)"}</span>
                </li>
              ))}
            </ul>
            <label className="auth-field">
              Confirmar senha
              <input
                type="password"
                name="confirm"
                autoComplete="new-password"
                required
                aria-invalid={mismatch || undefined}
                value={confirm}
                onChange={(event) => {
                  setConfirm(event.target.value);
                }}
              />
              {mismatch && (
                <span className="auth-error" role="alert">
                  As senhas não conferem.
                </span>
              )}
            </label>
          </>
        )}
        {!signUp && (
          <Link className="auth-link auth-forgot" href="/esqueci-senha">
            Esqueceu a senha?
          </Link>
        )}
        <FormMessage error={error} notice={notice} />
        <button className="btn primary" type="submit" disabled={busy || !ready}>
          {signUp ? "Criar conta" : "Entrar"}
        </button>
      </form>
      <div className="auth-providers">
        <p className="auth-or">ou</p>
        <button
          className="btn"
          type="button"
          disabled={busy}
          onClick={() => void signInWithGoogle()}
        >
          <GoogleMark /> Continuar com Google
        </button>
        <button className="btn" type="button" disabled={busy} onClick={() => void sendLink()}>
          <MailMark /> Enviar link de acesso
        </button>
      </div>
      <button
        type="button"
        className="auth-link auth-switch"
        onClick={() => {
          switchTo(signUp ? "signIn" : "signUp");
        }}
      >
        {signUp ? "Já tem conta? Entrar" : "Ainda não tem conta? Criar conta"}
      </button>
    </>
  );
}

function GoogleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.1A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.44.34-2.1V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15A10.6 10.6 0 0 0 12 1 11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z"
      />
    </svg>
  );
}

function MailMark() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
    >
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </svg>
  );
}
