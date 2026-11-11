import { describe, expect, it } from "vitest";
import { passwordOk, passwordRules } from "./password";

describe("regras da senha nova", () => {
  it("marca cada regra enquanto a pessoa digita", () => {
    expect(passwordRules("abc")).toEqual({
      length: false,
      lower: true,
      upper: false,
      digit: false,
    });
    expect(passwordRules("Integracao2026")).toEqual({
      length: true,
      lower: true,
      upper: true,
      digit: true,
    });
  });

  it("só aceita quando todas valem", () => {
    expect(passwordOk("Integracao2026")).toBe(true);
    expect(passwordOk("integracao2026")).toBe(false);
    expect(passwordOk("Curta1")).toBe(false);
  });
});
