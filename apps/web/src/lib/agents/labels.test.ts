import { describe, expect, it } from "vitest";
import { agentState, collectionsText, lastSeenText } from "./labels";

const NOW = new Date("2026-11-09T12:00:00Z");
const base = { last_seen_at: null, registration_expires_at: null };

describe("agentState", () => {
  it("ativo com contato recente está conectado", () => {
    expect(
      agentState({ ...base, status: "active", last_seen_at: "2026-11-09T11:58:00Z" }, NOW),
    ).toEqual({
      label: "Conectado",
      tone: "success",
    });
  });
  it("ativo sem contato há mais de 15 min fica sem contato", () => {
    expect(
      agentState({ ...base, status: "active", last_seen_at: "2026-11-09T11:40:00Z" }, NOW).label,
    ).toBe("Sem contato");
  });
  it("pendente mostra se o token ainda vale", () => {
    expect(
      agentState(
        { ...base, status: "pending", registration_expires_at: "2026-11-10T00:00:00Z" },
        NOW,
      ).label,
    ).toBe("Aguardando registro");
    expect(
      agentState(
        { ...base, status: "pending", registration_expires_at: "2026-11-09T00:00:00Z" },
        NOW,
      ).label,
    ).toBe("Token vencido");
  });
  it("revogado", () => {
    expect(agentState({ ...base, status: "revoked" }, NOW)).toEqual({
      label: "Revogado",
      tone: "danger",
    });
  });
});

describe("textos", () => {
  it("último contato", () => {
    expect(lastSeenText(null, NOW)).toBe("nunca falou com a plataforma");
    expect(lastSeenText("2026-11-09T11:30:00Z", NOW)).toBe("há 30 min");
  });
  it("coletas autorizadas", () => {
    expect(collectionsText({ collections: [] })).toBe("nenhuma coleta autorizada");
    expect(
      collectionsText({
        collections: [
          { type: "directory", path: "/exports/sm58" },
          { type: "rfc_table", table: "EDIDS" },
          { type: "rfc_function", name: "Z_AID_READ_SLG1" },
        ],
      }),
    ).toBe("pasta /exports/sm58 · tabela EDIDS · função Z_AID_READ_SLG1");
  });
});
