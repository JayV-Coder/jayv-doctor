"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { downloadLabel, shareExpiry } from "@/lib/reports/labels";
import { createReport, reportStatus, shareReport } from "./actions";

const POLL_MS = 1000;
const POLL_TRIES = 30;

// Opções da Tela 19. Gerar é assíncrono: o pedido vai para a fila e a tela espera o arquivo
// ficar pronto (o worker leva poucos segundos) antes de baixar ou compartilhar.
export function ReportForm({ incidentId }: { incidentId: string }) {
  const router = useRouter();
  const [format, setFormat] = useState<"pdf" | "md">("pdf");
  const [timeline, setTimeline] = useState(true);
  const [excerpts, setExcerpts] = useState(false);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState<{ url: string; expires_at: string } | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();

  // Opção nova é outro pedido: chave nova, e o link anterior some da tela.
  function changed() {
    setKey(crypto.randomUUID());
    setLink(null);
  }

  async function ready(): Promise<string | null> {
    const created = await createReport(
      incidentId,
      { format, include_timeline: timeline, include_event_excerpts: excerpts },
      key,
    );
    if (!created.ok) {
      setError(created.error);
      return null;
    }
    for (let attempt = 0; attempt < POLL_TRIES; attempt += 1) {
      const status = await reportStatus(created.value);
      if (status === "ready") return created.value;
      if (status === "failed") break;
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    }
    setError("Não foi possível gerar o relatório. Tente de novo.");
    setKey(crypto.randomUUID());
    return null;
  }

  function run(then: (report: string) => Promise<void>) {
    setError(null);
    // Fora da transição: o aviso aparece já, não só quando ela termina.
    setProgress("Gerando o relatório…");
    startTransition(async () => {
      const report = await ready();
      if (report) await then(report);
      setProgress(null);
      router.refresh();
    });
  }

  return (
    <>
      <label className="field">
        Formato
        <select
          value={format}
          onChange={(event) => {
            setFormat(event.target.value === "md" ? "md" : "pdf");
            changed();
          }}
        >
          <option value="pdf">PDF</option>
          <option value="md">Markdown</option>
        </select>
      </label>
      <label className="option">
        <input
          type="checkbox"
          checked={timeline}
          onChange={() => {
            setTimeline(!timeline);
            changed();
          }}
        />
        Incluir timeline completa
      </label>
      <label className="option">
        <input
          type="checkbox"
          checked={excerpts}
          onChange={() => {
            setExcerpts(!excerpts);
            changed();
          }}
        />
        Incluir trechos de eventos (sanitizados)
      </label>
      {progress && (
        <p className="small" role="status">
          {progress}
        </p>
      )}
      <FormMessage error={error} />
      {link && (
        <div className="note" role="status">
          <p>Link criado ({shareExpiry(link.expires_at)}). Copie agora: ele não aparece de novo.</p>
          <label className="field">
            Link compartilhável
            <input
              readOnly
              value={link.url}
              onFocus={(event) => {
                event.target.select();
              }}
            />
          </label>
        </div>
      )}
      <div className="row-between">
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            run(async (report) => {
              const shared = await shareReport(incidentId, report);
              if (shared.ok) setLink(shared.value);
              else setError(shared.error);
            });
          }}
        >
          Compartilhar link
        </button>
        <button
          type="button"
          className="btn primary"
          disabled={busy}
          onClick={() => {
            run((report) => {
              window.location.assign(`/incidentes/${incidentId}/relatorio/${report}`);
              return Promise.resolve();
            });
          }}
        >
          {downloadLabel(format)}
        </button>
      </div>
    </>
  );
}
