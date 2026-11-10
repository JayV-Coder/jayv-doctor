"use client";

import { useState } from "react";
import { serviceAccountEmail } from "@/lib/connectors/credential";
import { buildSalesforceCredential } from "@/lib/connectors/salesforce";

// A credencial fica só na memória do componente até ser enviada: nunca em sessionStorage, cookie
// ou URL. O GCP recebe a chave JSON da Service Account; o Salesforce, os campos da Connected App
// (a chave PEM em várias linhas); os outros provedores, um texto.
export function CredentialField({
  provider,
  onChange,
}: {
  provider: string;
  onChange: (credential: string | null) => void;
}) {
  const [account, setAccount] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);

  if (provider === "salesforce") return <SalesforceCredential onChange={onChange} />;

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

function SalesforceCredential({ onChange }: { onChange: (credential: string | null) => void }) {
  const [auth, setAuth] = useState<"jwt_bearer" | "web_server">("jwt_bearer");
  const [fields, setFields] = useState({
    client_id: "",
    username: "",
    private_key: "",
    client_secret: "",
    refresh_token: "",
  });

  function change(next: Partial<typeof fields>, mode = auth) {
    const merged = { ...fields, ...next };
    setFields(merged);
    onChange(buildSalesforceCredential(mode, merged));
  }

  return (
    <>
      <label className="field">
        Autenticação
        <select
          value={auth}
          onChange={(event) => {
            const mode = event.currentTarget.value === "web_server" ? "web_server" : "jwt_bearer";
            setAuth(mode);
            change({}, mode);
          }}
        >
          <option value="jwt_bearer">JWT Bearer com certificado</option>
          <option value="web_server">Web Server Flow com refresh token</option>
        </select>
      </label>
      <label className="field">
        Consumer Key da Connected App
        <input
          autoComplete="off"
          value={fields.client_id}
          onChange={(event) => {
            change({ client_id: event.currentTarget.value });
          }}
        />
      </label>
      {auth === "jwt_bearer" ? (
        <>
          <label className="field">
            Usuário de integração
            <input
              type="email"
              autoComplete="off"
              value={fields.username}
              onChange={(event) => {
                change({ username: event.currentTarget.value });
              }}
            />
          </label>
          <label className="field">
            Chave privada do certificado (PEM)
            <textarea
              rows={4}
              spellCheck={false}
              value={fields.private_key}
              onChange={(event) => {
                change({ private_key: event.currentTarget.value });
              }}
            />
          </label>
        </>
      ) : (
        <>
          <label className="field">
            Consumer Secret
            <input
              type="password"
              autoComplete="off"
              value={fields.client_secret}
              onChange={(event) => {
                change({ client_secret: event.currentTarget.value });
              }}
            />
          </label>
          <label className="field">
            Refresh token
            <input
              type="password"
              autoComplete="off"
              value={fields.refresh_token}
              onChange={(event) => {
                change({ refresh_token: event.currentTarget.value });
              }}
            />
          </label>
        </>
      )}
    </>
  );
}
