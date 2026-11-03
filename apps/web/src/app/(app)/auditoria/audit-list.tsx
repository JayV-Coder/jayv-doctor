"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import type { AuditPage } from "@/lib/audit/api";
import { actorText, describeEntry, dotTone } from "@/lib/audit/labels";
import { formatDateTime } from "@/lib/format";
import { findAudit } from "./actions";

export function AuditList({ category, initial }: { category: string | null; initial: AuditPage }) {
  const [items, setItems] = useState(initial.items);
  const [cursor, setCursor] = useState(initial.next_cursor);
  // O termo fica só na memória da página: pode ser o e-mail de alguém.
  const [term, setTerm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();

  function run(q: string | null, after: string | null) {
    startTransition(async () => {
      const page = await findAudit(category, q, after).catch(() => null);
      if (page === null) {
        setError("Não foi possível buscar agora. Tente de novo.");
        return;
      }
      setError(null);
      setItems((current) => (after ? [...current, ...page.items] : page.items));
      setCursor(page.next_cursor);
    });
  }

  return (
    <>
      <form
        role="search"
        className="search-row"
        onSubmit={(event) => {
          event.preventDefault();
          run(term.trim() || null, null);
        }}
      >
        <label className="field">
          <span className="visually-hidden">Filtrar a auditoria</span>
          <input
            type="search"
            value={term}
            autoCapitalize="none"
            spellCheck={false}
            placeholder="Filtrar por usuário, ação ou recurso"
            onChange={(event) => {
              setTerm(event.currentTarget.value);
            }}
          />
        </label>
        <button className="btn" type="submit" disabled={busy}>
          Buscar
        </button>
      </form>
      <form method="post" action="/auditoria/exportar">
        <input type="hidden" name="category" value={category ?? ""} />
        <input type="hidden" name="q" value={term.trim()} />
        <button className="btn" type="submit">
          Exportar CSV
        </button>
      </form>
      <FormMessage error={error} />
      {items.length === 0 ? (
        <p className="muted small" role="status">
          Nenhum registro com esses filtros.
        </p>
      ) : (
        <ol className="timeline" aria-label="Trilha de auditoria">
          {items.map((item) => {
            const tone = dotTone(item.action);
            return (
              <li key={item.id} className="it">
                <span
                  className="dot"
                  data-tone={tone === "success" ? undefined : tone}
                  aria-hidden="true"
                />
                <div className="it-body">
                  <span>
                    <b>{actorText(item)}</b> {describeEntry(item)}
                  </span>
                  <span className="small">
                    {item.action}
                    {item.resource_id ? ` · ${item.resource_id.slice(0, 8)}` : ""}
                    {item.ip ? ` · IP ${item.ip}` : ""} ·{" "}
                    {formatDateTime(new Date(item.occurred_at), "UTC")} UTC
                  </span>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {cursor && (
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            run(term.trim() || null, cursor);
          }}
        >
          Carregar mais
        </button>
      )}
    </>
  );
}
