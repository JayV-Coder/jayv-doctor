import { describe, expect, it } from "vitest";
import {
  correlatedByLabel,
  errorSummary,
  eventSource,
  durationText,
  executionTitle,
  highlightJson,
  sanitizationLines,
  severityTone,
  statusLabel,
  statusTone,
  timeOfDay,
} from "./labels";

describe("status", () => {
  it("texto e cor dizem o mesmo", () => {
    expect(statusLabel("failed")).toBe("Falhou");
    expect(statusTone("failed")).toBe("danger");
    expect(statusLabel("success")).toBe("Sucesso");
    expect(statusLabel("pending_confirmation")).toBe("Pendente de confirmação");
    expect(statusTone("pending_confirmation")).toBe("warning");
    expect(statusLabel("unknown")).toBe("Indeterminada");
  });
});

describe("durationText", () => {
  it("em pt-BR, da escala certa", () => {
    expect(durationText(250)).toBe("250 ms");
    expect(durationText(1200)).toBe("1,2 s");
    expect(durationText(30412)).toBe("30,4 s");
    expect(durationText(125_000)).toBe("2 min 5 s");
  });
});

describe("timeOfDay", () => {
  it("hora em UTC com milissegundos, como na Timeline do mockup", () => {
    expect(timeOfDay("2026-11-02T14:02:01.120Z")).toBe("14:02:01.120");
  });
});

describe("executionTitle", () => {
  it("usa execution_id e trace quando há; senão, o começo do id", () => {
    expect(executionTitle("abc", { execution_id: ["exec-123"], trace_id: ["trace-abc"] })).toBe(
      "exec-123 · trace-abc",
    );
    expect(executionTitle("0190f3a1-7b2c", {})).toBe("Execução 0190f3a1");
  });
});

describe("correlatedByLabel", () => {
  it("diz a estratégia, e avisa a fraca", () => {
    expect(correlatedByLabel("execution_id")).toBe("por execution_id");
    expect(correlatedByLabel("business_reference")).toBe("pela Referência");
    expect(correlatedByLabel("temporal_proximity")).toBe("por proximidade (fraca)");
    expect(correlatedByLabel(null)).toBe("sem correlação");
  });
});

describe("severityTone", () => {
  it("ERROR e CRITICAL em vermelho, WARNING em atenção", () => {
    expect(severityTone("CRITICAL")).toBe("danger");
    expect(severityTone("WARNING")).toBe("warning");
    expect(severityTone("INFO")).toBe("neutral");
  });
});

describe("sanitizationLines", () => {
  it("traduz todos os tipos, e o desconhecido sem expor o nome interno", () => {
    expect(sanitizationLines({ counts: { telefone: 2, cartao: 1, misterio: 1 } })).toEqual([
      "2 telefones removidos",
      "1 cartão removido",
      "1 dado sensível removido",
    ]);
  });

  it("resume o que a Sanitização tirou", () => {
    expect(sanitizationLines({ counts: { bearer: 1, referencia: 2, cpf: 1 } })).toEqual([
      "1 token Bearer removido",
      "1 CPF removido",
      "2 Referências de negócio em HMAC",
    ]);
    expect(sanitizationLines({ counts: {}, truncated: true })).toEqual([
      "Nada sensível encontrado",
      "Conteúdo longo truncado",
    ]);
    expect(sanitizationLines(null)).toEqual(["Nada sensível encontrado"]);
  });
});

describe("highlightJson", () => {
  it("separa chaves, textos, números e literais", () => {
    expect(highlightJson({ a: "x", n: 5, ok: true, z: null })).toEqual([
      { kind: "plain", text: "{\n  " },
      { kind: "key", text: '"a"' },
      { kind: "plain", text: ": " },
      { kind: "string", text: '"x"' },
      { kind: "plain", text: ",\n  " },
      { kind: "key", text: '"n"' },
      { kind: "plain", text: ": " },
      { kind: "number", text: "5" },
      { kind: "plain", text: ",\n  " },
      { kind: "key", text: '"ok"' },
      { kind: "plain", text: ": " },
      { kind: "literal", text: "true" },
      { kind: "plain", text: ",\n  " },
      { kind: "key", text: '"z"' },
      { kind: "plain", text: ": " },
      { kind: "literal", text: "null" },
      { kind: "plain", text: "\n}" },
    ]);
  });

  it("marca o que a Sanitização trocou", () => {
    const tokens = highlightJson({ authorization: "[REMOVIDO:bearer]" });
    expect(tokens.find((token) => token.kind === "redacted")?.text).toBe('"[REMOVIDO:bearer]"');
  });
});

describe("eventSource e errorSummary", () => {
  it("tiram texto de campos que podem vir em qualquer formato", () => {
    expect(eventSource({ provider: "gcp", service: "sap-order-sync" })).toBe("sap-order-sync");
    expect(eventSource({ provider: "sap" })).toBe("sap");
    expect(eventSource({ service: { nested: true } })).toBe("origem desconhecida");
    expect(errorSummary({ category: "TIMEOUT", http_status: 504 })).toBe("HTTP 504 TIMEOUT");
    expect(errorSummary({ message: "x" })).toBeNull();
    expect(errorSummary(null)).toBeNull();
  });
});
