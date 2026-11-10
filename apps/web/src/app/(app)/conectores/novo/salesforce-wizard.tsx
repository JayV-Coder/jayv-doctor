"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition, type ReactNode } from "react";
import { FormMessage } from "@/components/auth-shell";
import type { Integration } from "@/lib/api";
import { INTERVALS, intervalLabel } from "@/lib/connectors/labels";
import {
  EMPTY_SALESFORCE,
  SOURCES,
  buildSalesforceConfig,
  buildSalesforceCredential,
  probeConfig,
  validField,
  validObject,
  type SalesforceDraft,
  type SourceId,
} from "@/lib/connectors/salesforce";
import { environmentLabel } from "@/lib/integrations/labels";
import { createConnector, testNewConnection, type TestOutcome } from "../actions";

type IntegrationOption = Pick<Integration, "id" | "name" | "environment">;

const TITLES = ["Org", "Credencial", "Fontes", "Ativar"] as const;
const OFFLINE: TestOutcome = { ok: false, message: "Sem conexão. Tente de novo." };

// Tela 12 para o Salesforce (#37): a credencial da Connected App fica só na memória e vai para o
// cofre ao ativar; nenhuma consulta é escrita aqui, só escolhida da allowlist.
export function SalesforceWizard({ integrations }: { integrations: IntegrationOption[] }) {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [draft, setDraft] = useState<SalesforceDraft>(EMPTY_SALESFORCE);
  const [secret, setSecret] = useState({
    client_id: "",
    username: "",
    private_key: "",
    client_secret: "",
    refresh_token: "",
  });
  const [connection, setConnection] = useState<TestOutcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const credential = buildSalesforceCredential(draft.auth, secret);
  const available = connection?.capabilities ?? {};

  function update(change: Partial<SalesforceDraft>) {
    setDraft({ ...draft, ...change });
    setError(null);
  }

  function changeSecret(change: Partial<typeof secret>) {
    setSecret({ ...secret, ...change });
    setConnection(null);
  }

  function toggle(source: SourceId, on: boolean) {
    update({
      sources: on ? [...draft.sources, source] : draft.sources.filter((s) => s !== source),
    });
  }

  function test() {
    if (credential === null) return;
    startTransition(async () => {
      const outcome = await testNewConnection(probeConfig(draft), credential, "salesforce").catch(
        () => OFFLINE,
      );
      setConnection(outcome);
      // Já marca o que a org tem.
      const found = outcome.capabilities ?? {};
      update({ sources: SOURCES.map(({ id }) => id).filter((id) => found[id]) });
    });
  }

  function activate() {
    if (credential === null) return;
    startTransition(async () => {
      const result = await createConnector({
        provider: "salesforce",
        integration_id: draft.integration_id,
        name: draft.name.trim() || "Salesforce",
        config: buildSalesforceConfig(draft),
        sync_interval_seconds: draft.sync_interval_seconds,
        credential,
      }).catch(() => ({ error: OFFLINE.message }));
      if ("error" in result) {
        setError(result.error);
        return;
      }
      router.push(`/conectores/${result.id}`);
    });
  }

  return (
    <div className="stack wizard">
      <div className="row-between">
        <Link className="small" href="/conectores">
          ‹ Conectores
        </Link>
        <span className="label">Salesforce · passo {step} de 4</span>
      </div>
      <div className="steps" aria-hidden="true">
        {TITLES.map((title, index) => (
          <i key={title} className={index < step ? "on" : undefined} />
        ))}
      </div>
      <h2 className="title">
        <span className="logo-mark">❯</span> {TITLES[step - 1]}
      </h2>

      {step === 1 && (
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            setStep(2);
          }}
        >
          <label className="field">
            Nome do conector
            <input
              minLength={2}
              maxLength={80}
              placeholder="Salesforce produção"
              value={draft.name}
              onChange={(event) => {
                update({ name: event.currentTarget.value });
              }}
            />
          </label>
          <label className="field">
            Ambiente da org
            <select
              value={draft.environment}
              onChange={(event) => {
                update({
                  environment: event.currentTarget.value === "sandbox" ? "sandbox" : "production",
                });
                setConnection(null);
              }}
            >
              <option value="production">Produção (login.salesforce.com)</option>
              <option value="sandbox">Sandbox (test.salesforce.com)</option>
            </select>
          </label>
          <label className="field">
            Objeto de log de integração (opcional)
            <input
              autoCapitalize="none"
              spellCheck={false}
              placeholder="Integration_Log__c"
              value={draft.object}
              aria-invalid={!validObject(draft.object)}
              onChange={(event) => {
                update({ object: event.currentTarget.value.trim() });
                setConnection(null);
              }}
            />
          </label>
          <p className="muted small">
            Objeto customizado da sua org onde as integrações registram cada chamada.
          </p>
          <Actions>
            <Link className="btn" href="/conectores">
              Cancelar
            </Link>
            <button className="btn primary" type="submit" disabled={!validObject(draft.object)}>
              Continuar
            </button>
          </Actions>
        </form>
      )}

      {step === 2 && (
        <div className="stack">
          <fieldset className="choice">
            <legend className="label">Autenticação da Connected App</legend>
            <label className="option">
              <input
                type="radio"
                name="auth"
                checked={draft.auth === "jwt_bearer"}
                onChange={() => {
                  update({ auth: "jwt_bearer" });
                  setConnection(null);
                }}
              />
              JWT Bearer com certificado (recomendado, sem senha)
            </label>
            <label className="option">
              <input
                type="radio"
                name="auth"
                checked={draft.auth === "web_server"}
                onChange={() => {
                  update({ auth: "web_server" });
                  setConnection(null);
                }}
              />
              Web Server Flow com refresh token
            </label>
          </fieldset>
          <label className="field">
            Consumer Key da Connected App
            <input
              autoCapitalize="none"
              spellCheck={false}
              value={secret.client_id}
              onChange={(event) => {
                changeSecret({ client_id: event.currentTarget.value });
              }}
            />
          </label>
          {draft.auth === "jwt_bearer" ? (
            <>
              <label className="field">
                Usuário de integração
                <input
                  type="email"
                  autoCapitalize="none"
                  value={secret.username}
                  onChange={(event) => {
                    changeSecret({ username: event.currentTarget.value });
                  }}
                />
              </label>
              <label className="field">
                Chave privada do certificado (PEM)
                <textarea
                  rows={4}
                  spellCheck={false}
                  value={secret.private_key}
                  onChange={(event) => {
                    changeSecret({ private_key: event.currentTarget.value });
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
                  value={secret.client_secret}
                  onChange={(event) => {
                    changeSecret({ client_secret: event.currentTarget.value });
                  }}
                />
              </label>
              <label className="field">
                Refresh token
                <input
                  type="password"
                  value={secret.refresh_token}
                  onChange={(event) => {
                    changeSecret({ refresh_token: event.currentTarget.value });
                  }}
                />
              </label>
            </>
          )}
          <p className="muted small">
            Guardada no cofre do Supabase (Vault); nenhuma tela a mostra de novo.
          </p>
          <FormMessage
            error={connection && !connection.ok ? connection.message : null}
            notice={connection?.ok ? connection.message : null}
          />
          <button
            type="button"
            className="btn"
            disabled={busy || credential === null}
            onClick={test}
          >
            Testar conexão
          </button>
          <Actions>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setStep(1);
              }}
            >
              Voltar
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={!connection?.ok}
              onClick={() => {
                setStep(3);
              }}
            >
              Continuar
            </button>
          </Actions>
        </div>
      )}

      {step === 3 && (
        <div className="stack">
          <fieldset className="choice" aria-label="Fontes">
            <legend className="label">Fontes desta org</legend>
            {SOURCES.map(({ id, label }) => (
              <label key={id} className="option">
                <input
                  type="checkbox"
                  checked={draft.sources.includes(id)}
                  disabled={!available[id]}
                  onChange={(event) => {
                    toggle(id, event.currentTarget.checked);
                  }}
                />
                {label}
                {!available[id] && <span className="small"> · indisponível nesta org</span>}
              </label>
            ))}
          </fieldset>
          {draft.sources.includes("integration_log") && (
            <div className="grid2">
              <label className="field">
                Campo da mensagem
                <input
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder="Message__c"
                  value={draft.message_field}
                  aria-invalid={!validField(draft.message_field)}
                  onChange={(event) => {
                    update({ message_field: event.currentTarget.value.trim() });
                  }}
                />
              </label>
              <label className="field">
                Campo da severidade
                <input
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder="Level__c"
                  value={draft.severity_field}
                  aria-invalid={!validField(draft.severity_field)}
                  onChange={(event) => {
                    update({ severity_field: event.currentTarget.value.trim() });
                  }}
                />
              </label>
            </div>
          )}
          <label className="field">
            Intervalo
            <select
              value={draft.sync_interval_seconds}
              onChange={(event) => {
                update({ sync_interval_seconds: Number(event.currentTarget.value) });
              }}
            >
              {INTERVALS.map((seconds) => (
                <option key={seconds} value={seconds}>
                  {intervalLabel(seconds)}
                </option>
              ))}
            </select>
          </label>
          <p className="muted small">
            A coleta pausa sozinha quando o uso da API da org chega a 80% do limite diário e volta
            na janela seguinte.
          </p>
          <Actions>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setStep(2);
              }}
            >
              Voltar
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={
                draft.sources.length === 0 ||
                !validField(draft.message_field) ||
                !validField(draft.severity_field)
              }
              onClick={() => {
                setStep(4);
              }}
            >
              Continuar
            </button>
          </Actions>
        </div>
      )}

      {step === 4 && (
        <div className="stack">
          <label className="field">
            Integração vinculada
            <select
              required
              value={draft.integration_id}
              onChange={(event) => {
                update({ integration_id: event.currentTarget.value });
              }}
            >
              <option value="" disabled>
                Selecione
              </option>
              {integrations.map((integration) => (
                <option key={integration.id} value={integration.id}>
                  {integration.name} · {environmentLabel(integration.environment)}
                </option>
              ))}
            </select>
          </label>
          <FormMessage error={error} />
          <Actions>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setStep(3);
              }}
            >
              Voltar
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={busy || draft.integration_id === "" || credential === null}
              onClick={activate}
            >
              Ativar conector
            </button>
          </Actions>
        </div>
      )}
    </div>
  );
}

function Actions({ children }: { children: ReactNode }) {
  return <div className="wizard-actions">{children}</div>;
}
