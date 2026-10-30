"use client";

import { useState, type SubmitEvent } from "react";
import { AuthShell, FormMessage, Win } from "@/components/auth-shell";
import { OtpInput } from "@/components/otp-input";
import { authErrorMessage } from "@/lib/auth/messages";
import { EMPTY_OTP } from "@/lib/auth/otp";
import { createClient } from "@/lib/supabase/client";

export default function VerifyMfaPage() {
  const [digits, setDigits] = useState<readonly string[]>(EMPTY_OTP);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const { mfa } = createClient().auth;
    const { data } = await mfa.listFactors();
    const factors = data?.totp ?? [];
    const code = digits.join("");
    // Com fator de reserva, o código pode ser de qualquer um dos apps cadastrados.
    for (const factor of factors) {
      const result = await mfa.challengeAndVerify({ factorId: factor.id, code });
      if (!result.error) {
        window.location.assign("/");
        return;
      }
      setError(authErrorMessage(result.error));
    }
    setDigits(EMPTY_OTP);
    setBusy(false);
  }

  return (
    <AuthShell>
      <Win title="verificação · mfa">
        <form className="stack" onSubmit={(event) => void submit(event)}>
          <p className="small">Digite o código de 6 dígitos do app autenticador.</p>
          <OtpInput digits={digits} onChange={setDigits} />
          <FormMessage error={error} />
          <button className="btn primary" type="submit" disabled={busy || digits.includes("")}>
            Verificar
          </button>
        </form>
      </Win>
      <form action="/auth/sair" method="post">
        <button className="btn" type="submit">
          Sair
        </button>
      </form>
    </AuthShell>
  );
}
