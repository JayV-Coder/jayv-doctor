import { describe, expect, it } from "vitest";
import { actorText, describeEntry, dotTone } from "./labels";

const base = {
  actor_type: "user" as const,
  actor_label: "julia@acme.test",
  resource_type: "membership",
  resource_id: "m1",
  before: null,
  after: null,
};

describe("Trilha de auditoria", () => {
  it("ação em português, com o antes e o depois do Papel", () => {
    expect(
      describeEntry({
        ...base,
        action: "membership.role_changed",
        before: { role: "analyst" },
        after: { role: "viewer" },
      }),
    ).toBe("alterou o papel de um membro: Analyst → Viewer");
    expect(describeEntry({ ...base, action: "vault.secret_read" })).toBe(
      "leu a credencial do Conector",
    );
    expect(describeEntry({ ...base, action: "auth.login" })).toBe("entrou");
    expect(describeEntry({ ...base, action: "algo.novo" })).toBe("algo.novo");
  });

  it("ator: e-mail, Sistema ou worker", () => {
    expect(actorText(base)).toBe("julia@acme.test");
    expect(actorText({ ...base, actor_type: "system", actor_label: null })).toBe("Sistema");
    expect(actorText({ ...base, actor_type: "worker", actor_label: null })).toBe("Worker");
    expect(actorText({ ...base, actor_label: null })).toBe("Usuário removido");
  });

  it("cor do ponto da timeline pela gravidade", () => {
    expect(dotTone("membership.role_changed")).toBe("danger");
    expect(dotTone("diagnosis.reviewed")).toBe("success");
    expect(dotTone("auth.login")).toBe("neutral");
  });
});
