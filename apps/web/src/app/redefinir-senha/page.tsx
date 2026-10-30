"use client";

import { useState, type SubmitEvent } from "react";
import { AuthShell, FormMessage } from "@/components/auth-shell";
import { authErrorMessage } from "@/lib/auth/messages";
import { createClient } from "@/lib/supabase/client";

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const result = await createClient().auth.updateUser({ password });
    if (!result.error) {
      window.location.assign("/");
      return;
    }
    setError(authErrorMessage(result.error));
    setBusy(false);
  }

  return (
    <AuthShell>
      <form className="stack" onSubmit={(event) => void submit(event)}>
        <label className="field">
          Nova senha
          <input
            type="password"
            autoComplete="new-password"
            minLength={12}
            required
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
            }}
          />
        </label>
        <p className="small">Ao menos 12 caracteres, com maiúsculas, minúsculas e números.</p>
        <FormMessage error={error} />
        <button className="btn primary" type="submit" disabled={busy}>
          Salvar nova senha
        </button>
      </form>
    </AuthShell>
  );
}
