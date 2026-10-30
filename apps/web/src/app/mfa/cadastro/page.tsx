"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { AuthShell, Win } from "@/components/auth-shell";
import { EnrollFactor } from "@/components/enroll-factor";
import { safeNext } from "@/lib/auth/gate";

function EnrollMfa() {
  const next = useSearchParams().get("next");
  return (
    <>
      <Win title="cadastro · mfa">
        <p className="small">Seu papel exige MFA. Cadastre um app autenticador para continuar.</p>
        <EnrollFactor
          onDone={() => {
            window.location.assign(next ? safeNext(next) : "/seguranca?primeiro=1");
          }}
        />
      </Win>
      <form action="/auth/sair" method="post">
        <button className="btn" type="submit">
          Sair
        </button>
      </form>
    </>
  );
}

export default function EnrollMfaPage() {
  return (
    <AuthShell>
      <Suspense>
        <EnrollMfa />
      </Suspense>
    </AuthShell>
  );
}
