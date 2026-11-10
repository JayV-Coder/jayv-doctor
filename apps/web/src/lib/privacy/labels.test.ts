import { describe, expect, it } from "vitest";
import {
  checkText,
  classLabel,
  daysText,
  deletionText,
  dpaText,
  reindexText,
  subprocessors,
} from "./labels";

describe("Retenção e LGPD", () => {
  it("classes e dias em português", () => {
    expect(classLabel("raw_logs")).toBe("Logs brutos");
    expect(classLabel("audit")).toBe("Auditoria");
    expect(daysText(1)).toBe("1 dia");
    expect(daysText(365)).toBe("365 dias");
  });

  it("subprocessadores conforme o provedor de IA da Organização", () => {
    const anthropic = subprocessors("anthropic").map((item) => item.name);
    expect(anthropic).toContain("Anthropic");
    expect(anthropic).toContain("Voyage AI");
    expect(anthropic).not.toContain("Google Vertex AI");
    const vertex = subprocessors("vertex").map((item) => item.name);
    expect(vertex).toContain("Google Vertex AI");
    expect(vertex).not.toContain("Anthropic");
  });

  it("perfil de IA: subprocessadores, DPA, verificação e reindex", () => {
    expect(subprocessors("br_region").map((item) => item.name)).not.toContain("Voyage AI");
    expect(subprocessors("dedicated")[2]?.purpose).toContain("capacidade dedicada");
    expect(dpaText("standard")).toContain("Transferência internacional");
    expect(dpaText("vertex")).toContain("sem transferência internacional");
    expect(
      checkText({
        checked_at: "2026-11-10T06:00:00Z",
        ok: true,
        region: "southamerica-east1",
        detail: null,
      }),
    ).toEqual({ text: "Verificado em 10/11: southamerica-east1", ok: true });
    expect(
      checkText({ checked_at: "2026-11-10T06:00:00Z", ok: false, region: null, detail: "x" })?.ok,
    ).toBe(false);
    expect(reindexText({ total: 10, current: 10 })).toBeNull();
    expect(reindexText({ total: 10, current: 3 })).toContain("3 de 10 documentos");
  });

  it("data da exclusão agendada", () => {
    expect(deletionText("2026-11-10T14:00:00Z")).toBe("Exclusão total agendada para 10/11/2026");
  });
});
