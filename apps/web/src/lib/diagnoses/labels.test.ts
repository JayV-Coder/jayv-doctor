import { describe, expect, it } from "vitest";
import {
  active,
  changes,
  confidenceText,
  evidenceChip,
  evidenceHref,
  stageSteps,
  statusChip,
  systemLabel,
} from "./labels";

describe("Diagnóstico", () => {
  it("status em texto e tom, com a revisão humana", () => {
    expect(statusChip({ status: "published", requires_human_review: true })).toEqual({
      text: "Requer revisão",
      tone: "warning",
    });
    expect(statusChip({ status: "published", requires_human_review: false }).text).toBe(
      "Publicado",
    );
    expect(statusChip({ status: "inconclusive", requires_human_review: true }).text).toBe(
      "Inconclusivo",
    );
    expect(statusChip({ status: "failed_llm", requires_human_review: true }).text).toBe(
      "Só Regras (IA falhou)",
    );
    expect(statusChip({ status: "running", requires_human_review: true }).text).toBe(
      "Em andamento",
    );
  });

  it("etapas: as feitas, a atual e as que faltam; rules_only pula Base e IA", () => {
    expect(stageSteps("knowledge", "hybrid").map((s) => [s.label, s.state])).toEqual([
      ["Validando", "done"],
      ["Correlacionando", "done"],
      ["Aplicando Regras", "done"],
      ["Consultando base", "current"],
      ["Interpretando", "todo"],
      ["Verificando Evidências", "todo"],
    ]);
    expect(stageSteps("queued", "rules_only").map((s) => s.label)).toEqual([
      "Validando",
      "Correlacionando",
      "Aplicando Regras",
      "Verificando Evidências",
    ]);
    expect(stageSteps("llm", "hybrid", false).map((s) => s.label)).not.toContain(
      "Consultando base",
    );
    expect(active("queued")).toBe(true);
    expect(active("inconclusive")).toBe(false);
  });

  it("confiança com vírgula e sistema indeterminado", () => {
    expect(confidenceText(0.68)).toBe("0,68");
    expect(confidenceText(null)).toBe("—");
    expect(confidenceText(1.2)).toBe("1,00");
    expect(systemLabel(null)).toBe("Indeterminado");
    expect(systemLabel("sap")).toBe("SAP");
  });

  it("Evidência: chip pelo tipo e 1 toque até o Evento", () => {
    const rule = {
      kind: "rule_match" as const,
      label: "INT-003 · Timeout HTTP",
      event_id: "e1",
      event_timestamp: null,
      execution_id: "x1",
    };
    expect(evidenceChip(rule)).toBe("INT-003");
    expect(evidenceHref(rule)).toBe("/eventos/e1");
    expect(evidenceHref({ ...rule, event_timestamp: "2026-11-02T14:00:00Z" })).toBe(
      "/eventos/e1?em=2026-11-02T14%3A00%3A00Z",
    );
    const event = {
      kind: "event" as const,
      label: "BAPI · ERROR",
      event_id: "e2",
      event_timestamp: "2026-11-02T14:00:00Z",
      execution_id: "x1",
    };
    expect(evidenceChip(event)).toBe("Evento");
    expect(evidenceHref(event)).toBe("/eventos/e2?em=2026-11-02T14%3A00%3A00Z");
    expect(
      evidenceHref({ ...event, kind: "global_chunk", event_id: null, execution_id: null }),
    ).toBe("/conhecimento?aba=global");
    expect(evidenceHref({ ...rule, event_id: null, execution_id: null })).toBeNull();
  });

  it("diferenças entre versões", () => {
    const before = {
      version: 1,
      status: "inconclusive",
      classification: "TIMEOUT",
      confidence: 0.5,
      responsible_system: null,
      probable_cause: "A",
    };
    const after = { ...before, version: 2, status: "published", confidence: 0.74 };
    expect(changes(before, after)).toEqual([
      "Status: Inconclusivo → Publicado",
      "Confiança heurística: 0,50 → 0,74",
    ]);
    expect(changes(before, { ...before, version: 2 })).toEqual([]);
  });
});
