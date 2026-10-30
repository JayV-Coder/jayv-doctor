import { describe, expect, it } from "vitest";
import { toSessionState } from "./session";

describe("toSessionState", () => {
  it("trata claims ausentes como sessão anônima", () => {
    expect(toSessionState(null, null)).toEqual({
      hasSession: false,
      role: null,
      currentLevel: null,
      nextLevel: null,
    });
  });

  it("lê o Papel da claim tenant_role e os níveis do Auth", () => {
    const levels = { currentLevel: "aal1", nextLevel: "aal2" };
    expect(toSessionState({ tenant_role: "admin" }, levels)).toEqual({
      hasSession: true,
      role: "admin",
      currentLevel: "aal1",
      nextLevel: "aal2",
    });
  });

  it("não aceita Papel que não seja texto", () => {
    expect(toSessionState({ tenant_role: 1 }, null).role).toBeNull();
  });
});
