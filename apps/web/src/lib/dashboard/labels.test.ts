import { describe, expect, it } from "vitest";
import { bucketLabel, changeText, mttrText, peak, rateText } from "./labels";

describe("Dashboard", () => {
  it("MTTR em horas e minutos, e sem dado quando não houve resolução", () => {
    expect(mttrText(130)).toBe("2h10");
    expect(mttrText(45.4)).toBe("45 min");
    expect(mttrText(null)).toBe("—");
  });

  it("taxa de erro em pt-BR e sem inventar 0% num período vazio", () => {
    expect(rateText(0.034)).toBe("3,4%");
    expect(rateText(null)).toBe("sem Execuções");
  });

  it("variação com seta e sem comparação quando não há base", () => {
    expect(changeText(0.06, "vs. período anterior")).toBe("▲ 6% vs. período anterior");
    expect(changeText(-0.34, "vs. baseline")).toBe("▼ 34% vs. baseline");
    expect(changeText(null, "vs. baseline")).toBeNull();
  });

  it("rótulo do intervalo em UTC e o pico", () => {
    expect(bucketLabel("2026-11-03T14:00:00Z", "hour")).toBe("14h");
    expect(bucketLabel("2026-11-03T00:00:00Z", "day")).toBe("03/11");
    expect(
      peak([
        { start: "a", failed: 1, total: 2 },
        { start: "b", failed: 5, total: 9 },
      ])?.start,
    ).toBe("b");
    expect(peak([{ start: "a", failed: 0, total: 2 }])).toBeNull();
  });
});
