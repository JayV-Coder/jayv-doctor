import { describe, expect, it } from "vitest";
import { classLabel, daysText, deletionText, subprocessors } from "./labels";

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

  it("data da exclusão agendada", () => {
    expect(deletionText("2026-11-10T14:00:00Z")).toBe("Exclusão total agendada para 10/11/2026");
  });
});
