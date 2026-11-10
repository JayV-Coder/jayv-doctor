import { describe, expect, it } from "vitest";
import { applicationServerKey, quietText, ruleSend, ruleWhen } from "./labels";

const channels = [
  { id: "c1", type: "webpush", name: "Push do plantão" },
  { id: "c2", type: "slack", name: "#integracoes" },
];

describe("Tela 20: Regras de alerta", () => {
  it("quando", () => {
    expect(
      ruleWhen({ type: "incident", min_severity: "critical", environments: ["prd"] }, []),
    ).toBe("crítico · prd");
    expect(ruleWhen({ type: "incident", min_severity: "high", environments: [] }, [])).toBe(
      "alta ou mais · todos os Ambientes",
    );
    expect(
      ruleWhen({ type: "error_rate", threshold_pct: 5, minutes: 10, integrations: ["i1"] }, [
        { id: "i1", name: "Pedidos SF → SAP" },
      ]),
    ).toBe("erro > 5% em 10 min · Pedidos SF → SAP");
    expect(ruleWhen({ type: "connector_failing" }, [])).toBe("Conector em falha");
    expect(ruleWhen({ type: "diagnosis_review", minutes: 30 }, [])).toBe(
      "Diagnóstico sem revisão há 30 min",
    );
  });

  it("enviar", () => {
    expect(ruleSend(["c2", "c1", "sumiu"], channels)).toBe("Push, Slack");
    expect(ruleSend([], channels)).toBe("nenhum canal");
  });

  it("silêncio", () => {
    expect(quietText({ start: "22:00", end: "07:00" })).toBe(
      "22:00 às 07:00, exceto severidade crítica",
    );
    expect(quietText(null)).toBe("sem silêncio");
  });

  it("chave VAPID em base64url vira bytes", () => {
    expect([...applicationServerKey("AQID_-8")]).toEqual([1, 2, 3, 255, 239]);
  });
});
