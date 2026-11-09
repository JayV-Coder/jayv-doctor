import { describe, expect, it } from "vitest";
import { downloadLabel, previewName, reportLine, shareExpiry } from "./labels";

describe("Relatório técnico", () => {
  it("nome do arquivo e botão por formato", () => {
    expect(previewName(142, "pdf")).toBe("inc-0142.pdf · pré-visualização");
    expect(downloadLabel("pdf")).toBe("Baixar PDF");
    expect(downloadLabel("md")).toBe("Baixar Markdown");
  });

  it("linha do histórico", () => {
    expect(
      reportLine({
        format: "md",
        status: "ready",
        diagnosis_version: 2,
        created_at: "2026-11-05T15:00:00Z",
      }),
    ).toBe("Markdown · Diagnóstico v2 · 05/11/2026, 12:00");
    expect(
      reportLine({
        format: "pdf",
        status: "queued",
        diagnosis_version: null,
        created_at: "2026-11-05T15:00:00Z",
      }),
    ).toBe("PDF · sem Diagnóstico · 05/11/2026, 12:00 · gerando…");
    expect(
      reportLine({
        format: "pdf",
        status: "failed",
        diagnosis_version: 1,
        created_at: "2026-11-05T15:00:00Z",
      }),
    ).toBe("PDF · Diagnóstico v1 · 05/11/2026, 12:00 · falhou");
  });

  it("validade do link", () => {
    expect(shareExpiry("2026-11-12T15:00:00Z")).toBe("vale até 12/11/2026, 12:00");
  });
});
