"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { Chip } from "@/components/ui/chip";
import { searchKnowledge, type Hit } from "./actions";

export function KnowledgeSearch() {
  const [term, setTerm] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [mode, setMode] = useState<"hybrid" | "text">("hybrid");
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();

  return (
    <>
      <form
        role="search"
        className="search-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (term.trim().length < 2) return;
          startTransition(async () => {
            const found = await searchKnowledge(term.trim()).catch(() => null);
            setError(found ? null : "Não foi possível buscar agora.");
            setHits(found?.items ?? null);
            setMode(found?.mode ?? "hybrid");
          });
        }}
      >
        <label className="field">
          <span className="visually-hidden">Buscar na Base de conhecimento</span>
          <input
            type="search"
            value={term}
            placeholder="Buscar em documentos e na Base global"
            onChange={(event) => {
              setTerm(event.currentTarget.value);
            }}
          />
        </label>
        <button className="btn" type="submit" disabled={busy}>
          Buscar
        </button>
      </form>
      <FormMessage error={error} />
      {hits && (
        <section aria-label="Resultados da busca" className="stack">
          {mode === "text" && (
            <p className="muted small">
              Busca só por texto: a busca semântica está indisponível agora.
            </p>
          )}
          {hits.length === 0 && <p className="muted small">Nada encontrado.</p>}
          {hits.map((hit, index) => (
            <article key={`${hit.document_id}-${String(index)}`} className="card">
              <span className="row-between">
                <span className="t">{hit.title}</span>
                <Chip tone={hit.origin === "global" ? "info" : "neutral"}>
                  {hit.origin === "global" ? "Base global" : "Minha organização"}
                </Chip>
              </span>
              {hit.heading && <span className="small">{hit.heading}</span>}
              <p className="small">{hit.excerpt}</p>
            </article>
          ))}
        </section>
      )}
    </>
  );
}
