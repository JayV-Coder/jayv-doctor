"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AuthShell, FormMessage, Win } from "@/components/auth-shell";
import { EnrollFactor } from "@/components/enroll-factor";

function Security() {
  const first = useSearchParams().get("primeiro") === "1";
  const [done, setDone] = useState(false);

  return (
    <>
      <Win title="segurança · mfa">
        <p className="small">
          Não há códigos de recuperação: quem perde o único app perde o acesso. Cadastre um segundo
          app, em outro aparelho, como reserva.
        </p>
        <FormMessage
          error={null}
          notice={
            done ? "App autenticador cadastrado." : first ? "MFA ativado. Falta a reserva." : null
          }
        />
        {done ? null : (
          <EnrollFactor
            onDone={() => {
              setDone(true);
            }}
          />
        )}
      </Win>
      <Link className="btn" href="/">
        Voltar
      </Link>
    </>
  );
}

export default function SecurityPage() {
  return (
    <AuthShell>
      <Suspense>
        <Security />
      </Suspense>
    </AuthShell>
  );
}
