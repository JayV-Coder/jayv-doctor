import { describe, expect, it } from "vitest";
import { authErrorMessage } from "./messages";

describe("authErrorMessage", () => {
  it("traduz os códigos conhecidos do Supabase Auth", () => {
    expect(authErrorMessage({ code: "invalid_credentials" })).toBe("E-mail ou senha incorretos.");
    expect(authErrorMessage({ code: "mfa_verification_failed" })).toBe(
      "Código incorreto ou expirado.",
    );
  });

  it("não vaza a mensagem crua em erro desconhecido", () => {
    const error = { code: "unexpected_failure", message: "pq: relation does not exist" };
    expect(authErrorMessage(error)).toBe("Não foi possível concluir. Tente de novo.");
  });
});
