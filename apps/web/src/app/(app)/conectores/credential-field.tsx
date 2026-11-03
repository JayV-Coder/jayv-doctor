"use client";

import { useState } from "react";
import { serviceAccountEmail } from "@/lib/connectors/credential";

// A credencial fica só na memória do componente até ser enviada: nunca em sessionStorage, cookie
// ou URL. O GCP recebe a chave JSON da Service Account; os outros provedores, um texto.
export function CredentialField({
  provider,
  onChange,
}: {
  provider: string;
  onChange: (credential: string | null) => void;
}) {
  const [account, setAccount] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);

  if (provider !== "gcp") {
    return (
      <label className="field">
        Credencial
        <input
          type="password"
          autoComplete="off"
          required
          onChange={(event) => {
            onChange(event.currentTarget.value || null);
          }}
        />
      </label>
    );
  }

  return (
    <>
      <label className="field">
        Chave JSON da Service Account
        <input
          type="file"
          accept=".json,application/json"
          required
          onChange={(event) => {
            const file = event.currentTarget.files?.[0];
            void (file?.text() ?? Promise.resolve("")).then((text) => {
              const email = serviceAccountEmail(text);
              setAccount(email);
              setInvalid(text !== "" && email === null);
              onChange(email ? text : null);
            });
          }}
        />
      </label>
      {account && <p className="small">Chave de {account}.</p>}
      {invalid && (
        <p className="alert" role="alert">
          O arquivo não é uma chave JSON de Service Account do Google.
        </p>
      )}
    </>
  );
}
