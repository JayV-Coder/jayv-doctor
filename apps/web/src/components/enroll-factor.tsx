"use client";

import { QRCodeSVG } from "qrcode.react";
import { useState, type SubmitEvent } from "react";
import { FormMessage } from "@/components/auth-shell";
import { OtpInput } from "@/components/otp-input";
import { authErrorMessage } from "@/lib/auth/messages";
import { EMPTY_OTP } from "@/lib/auth/otp";
import { createClient } from "@/lib/supabase/client";

interface Enrollment {
  factorId: string;
  uri: string;
  secret: string;
}

export function EnrollFactor({ onDone }: { onDone: () => void }) {
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [digits, setDigits] = useState<readonly string[]>(EMPTY_OTP);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    const { mfa } = createClient().auth;
    // Um cadastro abandonado deixaria um fator pendente ocupando o nome.
    const { data: factors } = await mfa.listFactors();
    for (const factor of factors?.all ?? []) {
      if (factor.status === "unverified") await mfa.unenroll({ factorId: factor.id });
    }
    const { data, error: enrollError } = await mfa.enroll({
      factorType: "totp",
      friendlyName: `App ${crypto.randomUUID().slice(0, 8)}`,
    });
    if (enrollError) setError(authErrorMessage(enrollError));
    else setEnrollment({ factorId: data.id, uri: data.totp.uri, secret: data.totp.secret });
    setBusy(false);
  }

  async function verify(event: SubmitEvent) {
    event.preventDefault();
    if (!enrollment) return;
    setBusy(true);
    setError(null);
    const result = await createClient().auth.mfa.challengeAndVerify({
      factorId: enrollment.factorId,
      code: digits.join(""),
    });
    if (!result.error) {
      onDone();
      return;
    }
    setError(authErrorMessage(result.error));
    setDigits(EMPTY_OTP);
    setBusy(false);
  }

  if (!enrollment) {
    return (
      <>
        <FormMessage error={error} />
        <button className="btn primary" type="button" disabled={busy} onClick={() => void start()}>
          Gerar QR code
        </button>
      </>
    );
  }

  return (
    <form className="stack" onSubmit={(event) => void verify(event)}>
      <p className="small">Escaneie com o app autenticador e digite o código gerado.</p>
      <div className="qr">
        <QRCodeSVG value={enrollment.uri} size={176} title="QR code do fator de autenticação" />
      </div>
      <a className="btn" href={enrollment.uri}>
        Abrir no app autenticador
      </a>
      <p className="small">
        Chave manual: <code className="secret">{enrollment.secret}</code>
      </p>
      <OtpInput digits={digits} onChange={setDigits} />
      <FormMessage error={error} />
      <button className="btn primary" type="submit" disabled={busy || digits.includes("")}>
        Confirmar
      </button>
    </form>
  );
}
