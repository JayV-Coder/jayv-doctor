"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import type { PrivacySettings } from "@/lib/privacy/api";
import { classLabel, daysText, deletionText } from "@/lib/privacy/labels";
import { cancelDeletion, requestDeletion, setLlm, setRetention } from "./actions";

type Props = {
  settings: PrivacySettings;
  manager: boolean;
  owner: boolean;
  slug: string;
};

// Tela 16: retenção, envio ao LLM, subprocessadores, titular e exclusão total.
export function PrivacySection({ settings, manager, owner, slug }: Props) {
  return (
    <>
      <h2 className="label">Retenção</h2>
      <ul className="list" aria-label="Retenção">
        {settings.retention.map((item) => (
          <li key={item.data_class}>
            <div className="li">
              <span className="li-text">
                <span>{classLabel(item.data_class)}</span>
                <span className="small">
                  {item.days === item.default_days
                    ? "padrão"
                    : `padrão ${daysText(item.default_days)}`}
                </span>
              </span>
              <span className="small">{daysText(item.days)}</span>
              {manager && <RetentionEditor item={item} />}
            </div>
          </li>
        ))}
      </ul>

      <h2 className="label">LGPD e IA</h2>
      <LlmToggle enabled={settings.llm_enabled} manager={manager} />
      <ul className="list">
        <li>
          <Link className="li" href="/subprocessadores">
            <span className="li-text">
              <span>Subprocessadores</span>
            </span>
            <span aria-hidden="true">›</span>
          </Link>
        </li>
        {manager && (
          <li>
            <Link className="li" href="/titular">
              <span className="li-text">
                <span>Direitos do titular</span>
                <span className="small">Localizar e apagar Eventos de uma pessoa</span>
              </span>
              <span aria-hidden="true">›</span>
            </Link>
          </li>
        )}
      </ul>
      {settings.deletion && (
        <p className="alert" role="status">
          {deletionText(settings.deletion.scheduled_for)}. Até lá, o Owner pode cancelar.
        </p>
      )}
      {owner && <Deletion scheduled={settings.deletion !== null} slug={slug} />}
    </>
  );
}

function RetentionEditor({ item }: { item: PrivacySettings["retention"][number] }) {
  const [days, setDays] = useState(String(item.days));
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  return (
    <BottomSheet
      title={`Retenção de ${classLabel(item.data_class)}`}
      trigger="Alterar"
      triggerLabel={`Alterar a retenção de ${classLabel(item.data_class)}`}
      onClose={() => {
        setError(null);
      }}
    >
      <label className="field">
        Dias (de {item.min_days} a {item.max_days})
        <input
          type="number"
          inputMode="numeric"
          min={item.min_days}
          max={item.max_days}
          value={days}
          onChange={(event) => {
            setDays(event.currentTarget.value);
          }}
        />
      </label>
      <FormMessage error={error} />
      <button
        type="button"
        className="btn primary"
        disabled={busy}
        onClick={(event) => {
          const dialog = event.currentTarget.closest("dialog");
          startTransition(async () => {
            const failure = await setRetention(item.data_class, Number(days)).catch(
              () => "Sem conexão. Tente de novo.",
            );
            setError(failure);
            if (failure === null) dialog?.close();
          });
        }}
      >
        Salvar
      </button>
    </BottomSheet>
  );
}

function LlmToggle({ enabled, manager }: { enabled: boolean; manager: boolean }) {
  // Otimista: muda na hora e volta se a API recusar.
  const [checked, setChecked] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  return (
    <div className="stack">
      <label className="option">
        <input
          type="checkbox"
          role="switch"
          checked={checked}
          disabled={!manager || busy}
          onChange={(event) => {
            const next = event.currentTarget.checked;
            setChecked(next);
            startTransition(async () => {
              const failure = await setLlm(next).catch(() => "Sem conexão. Tente de novo.");
              setError(failure);
              if (failure !== null) setChecked(!next);
            });
          }}
        />
        <span>
          <strong>Enviar evidências ao LLM</strong>
          <span className="muted small">
            Desligado, nada vai ao provedor de IA: o Diagnóstico usa só as Regras e a Base busca só
            pelo texto.
          </span>
        </span>
      </label>
      <FormMessage error={error} />
    </div>
  );
}

function Deletion({ scheduled, slug }: { scheduled: boolean; slug: string }) {
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  if (scheduled) {
    return (
      <div className="stack">
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            startTransition(async () => {
              setError(await cancelDeletion().catch(() => "Sem conexão. Tente de novo."));
            });
          }}
        >
          Cancelar a exclusão
        </button>
        <FormMessage error={error} />
      </div>
    );
  }
  return (
    <BottomSheet
      title="Excluir a Organização"
      trigger="Solicitar exclusão total"
      onClose={() => {
        setError(null);
        setTyped("");
      }}
    >
      <p className="small">
        Depois de 7 dias, todos os dados do Doctor desta Organização são apagados: Eventos,
        Incidentes, Diagnósticos, Base de conhecimento, arquivos, credenciais e tokens. Não há como
        desfazer depois disso. Digite <b>{slug}</b> para confirmar.
      </p>
      <label className="field">
        Identificador da Organização
        <input
          value={typed}
          autoCapitalize="none"
          spellCheck={false}
          onChange={(event) => {
            setTyped(event.currentTarget.value);
          }}
        />
      </label>
      <FormMessage error={error} />
      <button
        type="button"
        className="btn primary"
        disabled={busy || typed.trim() !== slug}
        onClick={(event) => {
          const dialog = event.currentTarget.closest("dialog");
          startTransition(async () => {
            const failure = await requestDeletion(typed.trim()).catch(
              () => "Sem conexão. Tente de novo.",
            );
            setError(failure);
            if (failure === null) dialog?.close();
          });
        }}
      >
        Excluir em 7 dias
      </button>
    </BottomSheet>
  );
}
