"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition, type ReactNode } from "react";
import { FormMessage } from "@/components/auth-shell";
import type { Integration } from "@/lib/api";
import { environmentLabel } from "@/lib/integrations/labels";
import { INTERVALS, intervalLabel } from "@/lib/connectors/labels";
import {
  DRAFT_KEY,
  EMPTY_DRAFT,
  SEVERITIES,
  buildConfig,
  gcloudCommands,
  readDraft,
  validProject,
  type Draft,
} from "@/lib/connectors/wizard";
import { createConnector, testNewConnection, type TestOutcome } from "../actions";
import { CredentialField } from "../credential-field";
import { CopyCommand } from "./copy-command";

type IntegrationOption = Pick<Integration, "id" | "name" | "environment">;

const TITLES = ["Projeto", "Credencial", "Filtros de coleta", "Ativar"] as const;
const OFFLINE: TestOutcome = { ok: false, message: "Sem conexão. Tente de novo." };

function save(key: string, draft: Draft) {
  try {
    sessionStorage.setItem(key, JSON.stringify(draft));
  } catch {
    // Sem sessionStorage (janela privada, bloqueio): perde-se só o progresso.
  }
}

export function GcpWizard({
  tenantId,
  integrations,
}: {
  tenantId: string;
  integrations: IntegrationOption[];
}) {
  // Um rascunho por Organização: quem troca de Organização na mesma aba não leva a config junto.
  const key = `${DRAFT_KEY}:${tenantId}`;
  const router = useRouter();
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  // A credencial e os testes ficam só na memória: voltar à página pede a chave de novo.
  const [credential, setCredential] = useState<string | null>(null);
  const [connection, setConnection] = useState<TestOutcome | null>(null);
  const [preview, setPreview] = useState<TestOutcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resumed, setResumed] = useState(false);
  const [busy, startTransition] = useTransition();

  useEffect(() => {
    let saved = EMPTY_DRAFT;
    try {
      saved = readDraft(sessionStorage.getItem(key));
    } catch {
      // Sem sessionStorage (janela privada, bloqueio): o assistente funciona sem rascunho.
    }
    // A Integração do rascunho pode ter sido arquivada desde então.
    if (!integrations.some(({ id }) => id === saved.integration_id)) {
      saved = { ...saved, integration_id: "" };
    }
    if (saved.step > 2) setResumed(true);
    setDraft({ ...saved, step: saved.step > 2 ? 2 : saved.step });
  }, [key, integrations]);

  // Grava a cada mudança feita pela pessoa, e só aí: ativar apaga o rascunho de vez.
  function update(change: Partial<Draft>) {
    const next = { ...draft, ...change };
    setDraft(next);
    setError(null);
    save(key, next);
  }

  function go(step: Draft["step"]) {
    update({ step });
    setResumed(false);
  }

  const config = buildConfig(draft);

  function runTest(onResult: (outcome: TestOutcome) => void) {
    if (credential === null) return;
    startTransition(async () => {
      onResult(await testNewConnection(config, credential).catch(() => OFFLINE));
    });
  }

  function activate() {
    if (credential === null) return;
    startTransition(async () => {
      const result = await createConnector({
        integration_id: draft.integration_id,
        name: draft.name.trim() || draft.project_id,
        config,
        sync_interval_seconds: draft.sync_interval_seconds,
        credential,
      }).catch(() => ({ error: OFFLINE.message }));
      if ("error" in result) {
        setError(result.error);
        return;
      }
      try {
        sessionStorage.removeItem(key);
      } catch {
        // Sem sessionStorage não há rascunho a apagar.
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
        <span className="label">Google Cloud · passo {draft.step} de 4</span>
      </div>
      <div className="steps" aria-hidden="true">
        {TITLES.map((title, index) => (
          <i key={title} className={index < draft.step ? "on" : undefined} />
        ))}
      </div>
      <h2 className="title">
        <span className="logo-mark">❯</span> {TITLES[draft.step - 1]}
      </h2>

      {draft.step === 1 && (
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            go(2);
          }}
        >
          <label className="field">
            ID do projeto
            <input
              name="project_id"
              required
              autoCapitalize="none"
              spellCheck={false}
              pattern="[a-z][a-z0-9\-]{4,28}[a-z0-9]"
              value={draft.project_id}
              onChange={(event) => {
                update({ project_id: event.currentTarget.value.trim() });
                setConnection(null);
                setPreview(null);
              }}
            />
          </label>
          <p className="muted small">
            O ID aparece no seletor de projetos do console, como acme-integracoes.
          </p>
          <label className="field">
            Nome do conector
            <input
              name="name"
              minLength={2}
              maxLength={80}
              placeholder={draft.project_id || "acme-integracoes"}
              value={draft.name}
              onChange={(event) => {
                update({ name: event.currentTarget.value });
              }}
            />
          </label>
          <Actions>
            <Link className="btn" href="/conectores">
              Cancelar
            </Link>
            <button
              className="btn primary"
              type="submit"
              disabled={!validProject(draft.project_id)}
            >
              Continuar
            </button>
          </Actions>
        </form>
      )}

      {draft.step === 2 && (
        <div className="stack">
          {resumed && (
            <p className="alert notice" role="status">
              Seu progresso foi recuperado. A chave não fica guardada no rascunho: envie de novo.
            </p>
          )}
          <fieldset className="choice">
            <legend className="label">Método de credencial</legend>
            <div className="method" aria-disabled="true">
              <span>
                <b>Sem chave (impersonation)</b>
                <span className="small">
                  Em breve: exige uma identidade da plataforma só da sua Organização.
                </span>
              </span>
            </div>
            <div className="method chosen">
              <span>
                <b>Chave JSON de Service Account</b>
                <span className="small">
                  Guardada no cofre do Supabase (Vault); nenhuma tela a mostra de novo.
                </span>
              </span>
            </div>
          </fieldset>
          <p className="small">
            No Cloud Shell, crie uma Service Account só com leitura de logs e gere a chave:
          </p>
          {gcloudCommands(draft.project_id).map((command) => (
            <CopyCommand key={command} command={command} />
          ))}
          <CredentialField
            provider="gcp"
            onChange={(value) => {
              setCredential(value);
              setConnection(null);
              setPreview(null);
            }}
          />
          <FormMessage
            error={connection && !connection.ok ? connection.message : null}
            notice={connection?.ok ? connection.message : null}
          />
          <button
            type="button"
            className="btn"
            disabled={busy || credential === null}
            onClick={() => {
              runTest(setConnection);
            }}
          >
            Testar conexão
          </button>
          <Actions>
            <button
              type="button"
              className="btn"
              onClick={() => {
                go(1);
              }}
            >
              Voltar
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={!connection?.ok}
              onClick={() => {
                go(3);
              }}
            >
              Continuar
            </button>
          </Actions>
        </div>
      )}

      {draft.step === 3 && (
        <div className="stack">
          <Done>
            <span>projeto {draft.project_id}</span>
            <span>conexão testada</span>
          </Done>
          <label className="field">
            Serviços do Cloud Run (opcional)
            <input
              value={draft.services}
              placeholder="sap-order-sync, sf-customer-sync"
              autoCapitalize="none"
              spellCheck={false}
              onChange={(event) => {
                update({ services: event.currentTarget.value });
                setPreview(null);
              }}
            />
          </label>
          <label className="field">
            Severidade mínima
            <select
              value={draft.min_severity}
              onChange={(event) => {
                update({ min_severity: event.currentTarget.value as Draft["min_severity"] });
                setPreview(null);
              }}
            >
              {SEVERITIES.map((severity) => (
                <option key={severity} value={severity}>
                  {severity === "DEFAULT" ? "Todas" : severity}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Filtro avançado (consulta do Logging, opcional)
            <textarea
              rows={2}
              maxLength={2000}
              spellCheck={false}
              value={draft.filter}
              onChange={(event) => {
                update({ filter: event.currentTarget.value });
                setPreview(null);
              }}
            />
          </label>
          <div className="grid2">
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
            <label className="field">
              Backfill
              <select
                value={draft.backfill_hours}
                onChange={(event) => {
                  update({ backfill_hours: Number(event.currentTarget.value) === 168 ? 168 : 24 });
                }}
              >
                <option value={24}>Últimas 24 h</option>
                <option value={168}>7 dias</option>
              </select>
            </label>
          </div>
          <section className="win" aria-label="Pré-visualização">
            <div className="win-head">
              <span>pré-visualização</span>
            </div>
            <div className="win-body">
              <FormMessage
                error={preview && !preview.ok ? preview.message : null}
                notice={preview?.ok ? preview.message : null}
              />
              {!preview && (
                <p className="small">Confira quantos registros da última hora os filtros pegam.</p>
              )}
              <button
                type="button"
                className="btn"
                disabled={busy || credential === null}
                onClick={() => {
                  runTest(setPreview);
                }}
              >
                Pré-visualizar
              </button>
            </div>
          </section>
          <Actions>
            <button
              type="button"
              className="btn"
              onClick={() => {
                go(2);
              }}
            >
              Voltar
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={!preview?.ok}
              onClick={() => {
                go(4);
              }}
            >
              Continuar
            </button>
          </Actions>
        </div>
      )}

      {draft.step === 4 && (
        <div className="stack">
          <Done>
            <span>projeto {draft.project_id}</span>
            <span>conexão testada</span>
            <span>filtros pré-visualizados</span>
          </Done>
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
          <p className="muted small">
            Ao ativar, a credencial vai para o cofre e a primeira Sincronização começa em seguida,
            buscando {draft.backfill_hours === 168 ? "os últimos 7 dias" : "as últimas 24 h"}.
          </p>
          <FormMessage error={error} />
          <Actions>
            <button
              type="button"
              className="btn"
              onClick={() => {
                go(3);
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

function Done({ children }: { children: ReactNode }) {
  return <div className="card done">{children}</div>;
}
