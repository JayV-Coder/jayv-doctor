import { describe, expect, it } from "vitest";
import { callbackUrl } from "./urls";

describe("callbackUrl", () => {
  it("aponta para o callback do próprio site", () => {
    expect(callbackUrl("https://app.test")).toBe("https://app.test/auth/callback");
  });

  it("carrega o destino e tolera barra final", () => {
    expect(callbackUrl("https://app.test/", "/redefinir-senha")).toBe(
      "https://app.test/auth/callback?next=%2Fredefinir-senha",
    );
  });
});
