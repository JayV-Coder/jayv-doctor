import { describe, expect, it } from "vitest";
import { confidence, formatDateTime, formatNumber, formatPercent } from "./format";

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

describe("confidence", () => {
  it("rotula a confiança sempre como heurística", () => {
    expect(confidence(0.82)).toEqual({ percent: 82, text: "82% · heurística" });
  });

  it("limita a escala entre 0 e 100%", () => {
    expect(confidence(1.4)).toEqual({ percent: 100, text: "100% · heurística" });
    expect(confidence(-0.2)).toEqual({ percent: 0, text: "0% · heurística" });
  });

  it("arredonda a barra e o texto do mesmo jeito", () => {
    expect(confidence(0.825)).toEqual({ percent: 83, text: "83% · heurística" });
  });
});
