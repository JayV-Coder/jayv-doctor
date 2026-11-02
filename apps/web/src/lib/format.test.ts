import { describe, expect, it } from "vitest";
import { confidenceText, formatDateTime, formatNumber, formatPercent } from "./format";

describe("formatos pt-BR", () => {
  it("separa milhar com ponto", () => {
    expect(formatNumber(18402)).toBe("18.402");
  });

  it("escreve porcentagem com vírgula", () => {
    expect(formatPercent(0.034)).toBe("3,4%");
    expect(formatPercent(1)).toBe("100%");
  });

  it("mostra data e hora no fuso pedido", () => {
    const instant = new Date("2026-11-02T17:05:00Z");
    expect(formatDateTime(instant, "America/Sao_Paulo")).toBe("02/11/2026, 14:05");
    expect(formatDateTime(instant, "Europe/Lisbon")).toBe("02/11/2026, 17:05");
  });
});

describe("confidenceText", () => {
  it("rotula a confiança sempre como heurística", () => {
    expect(confidenceText(0.82)).toBe("82% · heurística");
  });

  it("limita a escala entre 0 e 100%", () => {
    expect(confidenceText(1.4)).toBe("100% · heurística");
    expect(confidenceText(-0.2)).toBe("0% · heurística");
  });
});
