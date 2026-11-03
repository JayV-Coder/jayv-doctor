import { describe, expect, it } from "vitest";
import {
  NEXT_STATUSES,
  ageText,
  incidentCode,
  severityLabel,
  severityTone,
  statusLabel,
} from "./labels";

describe("Incidente", () => {
  it("código com o número da Organização", () => {
    expect(incidentCode(142)).toBe("INC-0142");
    expect(incidentCode(12345)).toBe("INC-12345");
  });

  it("severidade e status em português, com tom", () => {
    expect(severityLabel("critical")).toBe("Crítico");
    expect(severityTone("critical")).toBe("danger");
    expect(severityTone("medium")).toBe("warning");
    expect(statusLabel("investigating")).toBe("Em análise");
    expect(statusLabel("dismissed")).toBe("Descartado");
  });

  it("transições oferecidas são as que o banco aceita", () => {
    expect(NEXT_STATUSES.open).toEqual(["investigating", "resolved", "dismissed"]);
    expect(NEXT_STATUSES.resolved).toEqual(["open"]);
  });

  it("idade desde a última ocorrência", () => {
    const now = new Date("2026-11-03T14:20:00Z");
    expect(ageText("2026-11-03T14:02:00Z", now)).toBe("18 min");
    expect(ageText("2026-11-03T13:00:00Z", now)).toBe("1 h");
    expect(ageText("2026-11-01T14:00:00Z", now)).toBe("2 d");
  });
});
