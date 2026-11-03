"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { Chip } from "@/components/ui/chip";
import type { IncidentPage, IncidentSummary } from "@/lib/incidents/api";
import {
  ageText,
  incidentCode,
  severityLabel,
  severityTone,
  statusLabel,
} from "@/lib/incidents/labels";
import { environmentLabel } from "@/lib/integrations/labels";
import { formatNumber } from "@/lib/format";
import { findIncidents } from "./actions";

export function IncidentList({
  filters,
  initial,
}: {
  filters: { status: string[]; severity: string[] };
  initial: IncidentPage;
}) {
  const [items, setItems] = useState(initial.items);
  const [cursor, setCursor] = useState(initial.next_cursor);
  // O termo fica só na memória da página: pode ser um nº de pedido.
  const [term, setTerm] = useState("");
  const [searched, setSearched] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const now = new Date();

  function run(q: string | null, after: string | null) {
    startTransition(async () => {
      const page = await findIncidents(filters, q, after).catch(() => null);
      if (page === null) {
        setError("Não foi possível buscar agora. Tente de novo.");
        return;
      }
      setError(null);
      setSearched(q);
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
          <span className="visually-hidden">Buscar Incidente</span>
          <input
            type="search"
            value={term}
            autoCapitalize="none"
            spellCheck={false}
            placeholder="INC-0142, trace ou nº do pedido"
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
      {items.length === 0 && (
        <p className="muted small" role="status">
          {searched ? "Nenhum Incidente para essa busca." : "Nenhum Incidente com esses filtros."}
        </p>
      )}
      {items.map((item) => (
        <Card key={item.id} item={item} now={now} />
      ))}
      {cursor && (
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            run(searched, cursor);
          }}
        >
          Carregar mais
        </button>
      )}
    </>
  );
}

function Card({ item, now }: { item: IncidentSummary; now: Date }) {
  const code = incidentCode(item.number);
  return (
    <Link
      className="card incident-card"
      href={`/incidentes/${item.id}`}
      aria-label={`${code} ${item.title}`}
    >
      <span className="row-between">
        <Chip tone={severityTone(item.severity)}>{severityLabel(item.severity)}</Chip>
        <span className="small">
          {code} · {ageText(item.last_seen_at, now)}
        </span>
      </span>
      <span className="t">{item.title}</span>
      <span className="row-wrap">
        <Chip tone="neutral">
          {item.category} · {item.rule_code}
        </Chip>
        <Chip tone="info">{statusLabel(item.status)}</Chip>
      </span>
      <span className="small">
        {item.integration_name} · {environmentLabel(item.environment)} ·{" "}
        {formatNumber(item.execution_count)} {item.execution_count === 1 ? "execução" : "execuções"}
      </span>
    </Link>
  );
}
