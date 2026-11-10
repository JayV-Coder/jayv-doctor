import { describe, expect, it } from "vitest";
import { jiraState, ticketText } from "./labels";

describe("chamados (ITSM)", () => {
  it("estado da conexão", () => {
    expect(jiraState(null)).toEqual({ label: "Não conectado", tone: "neutral" });
    expect(jiraState({ status: "pending", project_key: null }).label).toBe("Falta o projeto");
    expect(jiraState({ status: "active", project_key: "SUST" })).toEqual({
      label: "Conectado",
      tone: "success",
    });
    expect(jiraState({ status: "needs_reauth", project_key: "SUST" }).label).toBe(
      "Conecte de novo",
    );
  });

  it("chamado no Incidente", () => {
    expect(
      ticketText({ status: "creating", external_key: null, external_status: null, error: null }),
    ).toBe("Criando o chamado…");
    expect(
      ticketText({
        status: "open",
        external_key: "SUST-881",
        external_status: "Em atendimento",
        error: null,
      }),
    ).toBe("SUST-881 · Em atendimento");
    expect(
      ticketText({
        status: "failed",
        external_key: null,
        external_status: null,
        error: "projeto não existe",
      }),
    ).toBe("Não abriu: projeto não existe");
  });
});
