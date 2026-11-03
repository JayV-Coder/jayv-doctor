import { describe, expect, it } from "vitest";
import { readFilters, toSearch, toggleHref } from "./filters";

const INTEGRATION = "00000000-0000-4000-8000-0000000001a1";

describe("readFilters", () => {
  it("aceita só valores conhecidos", () => {
    expect(
      readFilters({ status: "failed", integracao: INTEGRATION, ambiente: "prd", periodo: "24h" }),
    ).toEqual({ status: "failed", integration: INTEGRATION, environment: "prd", period: "24h" });
    expect(readFilters({ status: "x", integracao: "nao-uuid", periodo: ["24h"] })).toEqual({
      status: undefined,
      integration: undefined,
      environment: undefined,
      period: undefined,
    });
  });
});

describe("toSearch", () => {
  it("o período vira o início da janela", () => {
    const now = new Date("2026-11-03T12:00:00Z");
    expect(toSearch({ status: "failed", period: "24h" }, now)).toEqual({
      status: "failed",
      integration_id: null,
      environment: null,
      from: "2026-11-02T12:00:00.000Z",
    });
  });
});

describe("toggleHref", () => {
  it("liga e desliga um chip sem perder os outros", () => {
    expect(toggleHref({ environment: "prd" }, "status", "failed")).toBe(
      "/execucoes?status=failed&ambiente=prd",
    );
    expect(toggleHref({ status: "failed" }, "status", "failed")).toBe("/execucoes");
  });
});
