import { describe, expect, it } from "vitest";
import { decideRedirect, safeNext } from "./gate";

const session = { hasSession: true, role: null, currentLevel: "aal1", nextLevel: "aal1" } as const;
const anonymous = { hasSession: false, role: null, currentLevel: null, nextLevel: null } as const;
const admin = { ...session, role: "admin" } as const;

describe("decideRedirect", () => {
  it("manda quem não tem sessão para o login", () => {
    expect(decideRedirect("/", anonymous)).toBe("/login");
  });

  it("deixa as telas públicas abertas sem sessão", () => {
    for (const path of ["/login", "/esqueci-senha", "/privacidade", "/auth/callback"]) {
      expect(decideRedirect(path, anonymous)).toBeNull();
    }
  });

  it("deixa um analista sem MFA entrar", () => {
    expect(decideRedirect("/", { ...session, role: "analyst" })).toBeNull();
  });

  it("obriga Admin e Owner sem fator a cadastrar antes de qualquer tela", () => {
    expect(decideRedirect("/", admin)).toBe("/mfa/cadastro");
    expect(decideRedirect("/privacidade", admin)).toBeNull();
    expect(decideRedirect("/redefinir-senha", admin)).toBe("/mfa/cadastro");
    expect(decideRedirect("/", { ...admin, role: "owner" })).toBe("/mfa/cadastro");
    expect(decideRedirect("/mfa/cadastro", admin)).toBeNull();
  });

  it("pede verificação a quem tem fator e está em aal1, seja qual for o Papel", () => {
    const pending = { ...session, nextLevel: "aal2" } as const;
    expect(decideRedirect("/", pending)).toBe("/mfa");
    expect(decideRedirect("/mfa/cadastro", pending)).toBe("/mfa");
    expect(decideRedirect("/mfa", pending)).toBeNull();
  });

  it("libera quem já verificou o MFA e tira das telas de entrada", () => {
    const verified = { ...admin, currentLevel: "aal2", nextLevel: "aal2" } as const;
    expect(decideRedirect("/", verified)).toBeNull();
    expect(decideRedirect("/login", verified)).toBe("/");
    expect(decideRedirect("/mfa", verified)).toBe("/");
  });

  it("nunca prende o logout", () => {
    expect(decideRedirect("/auth/sair", admin)).toBeNull();
  });
});

describe("safeNext", () => {
  it("aceita caminho interno", () => {
    expect(safeNext("/redefinir-senha")).toBe("/redefinir-senha");
  });

  it("recusa redirecionamento aberto", () => {
    for (const value of ["https://mal.test", "//mal.test", "/\\mal.test", "", null]) {
      expect(safeNext(value)).toBe("/");
    }
  });
});
