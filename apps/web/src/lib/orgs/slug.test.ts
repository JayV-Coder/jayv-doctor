import { describe, expect, it } from "vitest";
import { slugify } from "./slug";

describe("slugify", () => {
  it("gera o identificador a partir do nome, sem acentos", () => {
    expect(slugify("Indústria Meridional S.A.")).toBe("industria-meridional-s-a");
  });

  it("não deixa hífen nas pontas", () => {
    expect(slugify("  --Acme!! ")).toBe("acme");
  });

  it("respeita o limite de 48 caracteres sem terminar em hífen", () => {
    expect(slugify(`${"a".repeat(47)} b`)).toBe("a".repeat(47));
  });
});
