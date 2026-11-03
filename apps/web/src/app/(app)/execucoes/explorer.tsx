"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { Chip } from "@/components/ui/chip";
import { ListItem } from "@/components/ui/list-item";
import type { ExecutionPage, ExecutionSummary } from "@/lib/api";
import type { Filters } from "@/lib/executions/filters";
import {
  durationText,
  executionTitle,
  statusLabel,
  statusTone,
  timeOfDay,
} from "@/lib/executions/labels";
import { formatNumber } from "@/lib/format";
import { findExecutions } from "./actions";

const INCIDENT_TONES = { critical: "danger", high: "danger", medium: "warning", low: "neutral" };

export function Explorer({ filters, initial }: { filters: Filters; initial: ExecutionPage }) {
  const [items, setItems] = useState(initial.items);
  const [cursor, setCursor] = useState(initial.next_cursor);
  // O termo fica só na memória da página: nem URL, nem histórico, nem log.
  const [term, setTerm] = useState("");
  const [searched, setSearched] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();

  function run(q: string | null, after: string | null) {
    startTransition(async () => {
      const page = await findExecutions(filters, q, after).catch(() => null);
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
        <label className="field grow">
          <span className="visually-hidden">Buscar Execução</span>
          <input
            type="search"
            value={term}
            autoCapitalize="none"
            spellCheck={false}
            placeholder="trace, execution_id ou nº do pedido"
            onChange={(event) => {
              setTerm(event.currentTarget.value);
            }}
          />
        </label>
        <button className="btn" type="submit" disabled={busy}>
          Buscar
        </button>
      </form>
      <p className="muted small">
        O nº do pedido vira um código (HMAC) no servidor antes da busca: ele não fica guardado nem
        aparece nos logs.
      </p>
      <FormMessage error={error} />

      {items.length === 0 && (
        <p className="muted small" role="status">
          {searched ? "Nenhuma Execução para essa busca." : "Nenhuma Execução com esses filtros."}
        </p>
      )}
      {items.length > 0 && (
        <ul className="list" aria-label="Execuções">
          {items.map((item) => (
            <Row key={item.id} item={item} />
          ))}
        </ul>
      )}
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

function Row({ item }: { item: ExecutionSummary }) {
  const tone = statusTone(item.status);
  const detail = [
    statusLabel(item.status),
    durationText(item.duration_ms),
    `${formatNumber(item.event_count)} ${item.event_count === 1 ? "evento" : "eventos"}`,
    `${timeOfDay(item.first_event_at).slice(0, 5)} UTC`,
  ].join(" · ");
  return (
    <ListItem
      href={`/execucoes/${item.id}`}
      title={
        <>
          <span className="dot" data-tone={tone} aria-hidden="true" />
          {executionTitle(item.id, item.correlation_keys)}
        </>
      }
      detail={`${item.integration_name} · ${detail}`}
      trailing={
        item.incident ? (
          <Chip
            tone={
              INCIDENT_TONES[item.incident.severity as keyof typeof INCIDENT_TONES] as
                "danger" | "warning" | "neutral"
            }
          >
            Incidente
          </Chip>
        ) : undefined
      }
    />
  );
}
