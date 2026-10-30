import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { validateEvent } from "./event";

const fixtures = fileURLToPath(new URL("../fixtures/event.v1", import.meta.url));

function load(kind: "valid" | "invalid"): [string, unknown][] {
  const dir = join(fixtures, kind);
  return readdirSync(dir)
    .filter((name) => name.endsWith(".json"))
    .sort()
    .map((name) => [
      name.replace(/\.json$/, ""),
      JSON.parse(readFileSync(join(dir, name), "utf8")),
    ]);
}

describe("Contrato de evento v1", () => {
  it.each(load("valid"))("aceita a fixture válida %s", (_name, payload) => {
    const result = validateEvent(payload);

    expect(result.ok).toBe(true);
  });

  it.each(load("invalid"))("rejeita a fixture inválida %s", (_name, payload) => {
    const result = validateEvent(payload);

    expect(result.ok).toBe(false);
  });

  it("explica que tenant_id não é aceito", () => {
    const [, payload] = load("invalid").find(([name]) => name === "with-tenant-id") ?? [];

    const result = validateEvent(payload);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.some((error) => error.includes("tenant_id"))).toBe(true);
  });
});
