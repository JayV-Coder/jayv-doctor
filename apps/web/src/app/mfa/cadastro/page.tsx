"use client";

import { AuthShell, Win } from "@/components/auth-shell";
import { EnrollFactor } from "@/components/enroll-factor";

export default function EnrollMfaPage() {
  return (
    <AuthShell>
      <Win title="cadastro · mfa">
        <p className="small">Seu papel exige MFA. Cadastre um app autenticador para continuar.</p>
        <EnrollFactor
          onDone={() => {
            window.location.assign("/seguranca?primeiro=1");
          }}
        />
      </Win>
      <form action="/auth/sair" method="post">
        <button className="btn" type="submit">
          Sair
        </button>
      </form>
    </AuthShell>
  );
}
