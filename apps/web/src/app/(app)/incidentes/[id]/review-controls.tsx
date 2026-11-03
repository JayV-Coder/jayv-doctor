"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { promoteIncident, reviewDiagnosis } from "../actions";

const SYSTEMS = [
  ["", "Indeterminado"],
  ["sap", "SAP"],
  ["salesforce", "Salesforce"],
  ["gcp", "Google Cloud"],
  ["other", "Outro"],
] as const;

type Props = { incidentId: string; diagnosisId: string };

// Revisão humana (#26): Aceitar direto; Corrigir e Rejeitar pedem o porquê num bottom sheet. Cada
// ação tem a própria mensagem de erro e a própria chave de idempotência; fechar o painel recomeça.
export function ReviewControls({ incidentId, diagnosisId }: Props) {
  const accept = useReview(incidentId, diagnosisId);
  const correct = useReview(incidentId, diagnosisId);
  const reject = useReview(incidentId, diagnosisId);

  return (
    <section className="stack" aria-label="Revisão humana">
      <div className="row-wrap">
        <button
          type="button"
          className="btn primary"
          disabled={accept.busy}
          onClick={() => {
            accept.send({ verdict: "accepted" });
          }}
        >
          Aceitar
        </button>
        <BottomSheet title="Corrigir o Diagnóstico" trigger="Corrigir" onClose={correct.reset}>
          <CorrectionForm
            busy={correct.busy}
            onSubmit={(body, dialog) => {
              correct.send({ verdict: "corrected", ...body }, dialog);
            }}
          />
          <FormMessage error={correct.error} />
        </BottomSheet>
        <BottomSheet title="Rejeitar o Diagnóstico" trigger="Rejeitar" onClose={reject.reset}>
          <RejectForm
            busy={reject.busy}
            onSubmit={(comment, dialog) => {
              reject.send({ verdict: "rejected", comment }, dialog);
            }}
          />
          <FormMessage error={reject.error} />
        </BottomSheet>
      </div>
      <FormMessage error={accept.error} />
    </section>
  );
}

function useReview(incidentId: string, diagnosisId: string) {
  const [error, setError] = useState<string | null>(null);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [busy, startTransition] = useTransition();
  return {
    busy,
    error,
    reset: () => {
      setError(null);
      setKey(crypto.randomUUID());
    },
    send: (body: Parameters<typeof reviewDiagnosis>[2], dialog?: HTMLDialogElement | null) => {
      startTransition(async () => {
        const failure = await reviewDiagnosis(incidentId, diagnosisId, body, key).catch(
          () => "Sem conexão. Tente de novo.",
        );
        setError(failure);
        if (failure === null) {
          setKey(crypto.randomUUID());
          dialog?.close();
        }
      });
    },
  };
}

function CorrectionForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (
    body: {
      correct_category?: string | undefined;
      correct_cause?: string | undefined;
      responsible_system?: string | undefined;
      comment?: string | undefined;
    },
    dialog: HTMLDialogElement | null,
  ) => void;
}) {
  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const value = (name: string) => {
          const found = data.get(name);
          return typeof found === "string" && found.trim() ? found.trim() : undefined;
        };
        onSubmit(
          {
            correct_category: value("category")?.toUpperCase(),
            correct_cause: value("cause"),
            responsible_system: value("system"),
            comment: value("comment"),
          },
          event.currentTarget.closest("dialog"),
        );
      }}
    >
      <label className="field">
        Categoria correta
        <input name="category" placeholder="SAP_LOCK" autoCapitalize="characters" />
      </label>
      <label className="field">
        Causa correta
        <textarea name="cause" rows={3} maxLength={2000} />
      </label>
      <label className="field">
        Sistema responsável
        <select name="system" defaultValue="">
          {SYSTEMS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        Comentário
        <textarea name="comment" rows={2} maxLength={2000} />
      </label>
      <button type="submit" className="btn primary" disabled={busy}>
        Salvar correção
      </button>
    </form>
  );
}

function RejectForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (comment: string | undefined, dialog: HTMLDialogElement | null) => void;
}) {
  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        const found = new FormData(event.currentTarget).get("comment");
        const comment = typeof found === "string" && found.trim() ? found.trim() : undefined;
        onSubmit(comment, event.currentTarget.closest("dialog"));
      }}
    >
      <label className="field">
        Por que o Diagnóstico está errado?
        <textarea name="comment" rows={3} maxLength={2000} />
      </label>
      <button type="submit" className="btn primary" disabled={busy}>
        Rejeitar
      </button>
    </form>
  );
}

// Incidente resolvido com Diagnóstico aceito ou corrigido: o caso vai para a Base de conhecimento.
export function PromoteButton({ incidentId }: { incidentId: string }) {
  const [error, setError] = useState<string | null>(null);
  const [key] = useState(() => crypto.randomUUID());
  const [busy, startTransition] = useTransition();
  return (
    <div className="stack">
      <button
        type="button"
        className="btn"
        disabled={busy}
        onClick={() => {
          startTransition(async () => {
            setError(
              await promoteIncident(incidentId, key).catch(() => "Sem conexão. Tente de novo."),
            );
          });
        }}
      >
        Promover à Base de conhecimento
      </button>
      <FormMessage error={error} />
    </div>
  );
}
