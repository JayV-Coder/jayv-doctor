import { describe, expect, it } from "vitest";
import { parseTheme, themeCookie } from "./theme";

describe("parseTheme", () => {
  it("aceita só claro e escuro; o resto segue o sistema", () => {
    expect(parseTheme("light")).toBe("light");
    expect(parseTheme("dark")).toBe("dark");
    expect(parseTheme(undefined)).toBe("system");
    expect(parseTheme("roxo")).toBe("system");
  });
});

describe("themeCookie", () => {
  it("guarda a escolha por um ano", () => {
    expect(themeCookie("dark")).toBe("tema=dark; Path=/; Max-Age=31536000; SameSite=Lax");
  });

  it("apaga o cookie ao voltar para o tema do sistema", () => {
    expect(themeCookie("system")).toBe("tema=; Path=/; Max-Age=0; SameSite=Lax");
  });
});
