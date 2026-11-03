import { describe, expect, it } from "vitest";
import { contentTypeOf, documentDetail, kindLabel } from "./labels";

describe("Base de conhecimento", () => {
  it("formato pelo nome do arquivo, só os aceitos", () => {
    expect(contentTypeOf("Runbook.PDF")).toBe("application/pdf");
    expect(contentTypeOf("notas.md")).toBe("text/markdown");
    expect(contentTypeOf("contrato.docx")).toBe(
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    );
    expect(contentTypeOf("planilha.xlsx")).toBeNull();
  });

  it("chip do tipo", () => {
    expect(kindLabel({ source: "upload", content_type: "application/pdf" })).toBe("PDF");
    expect(kindLabel({ source: "incident", content_type: null })).toBe("INC");
  });

  it("status de indexação em texto", () => {
    expect(documentDetail({ status: "ready", chunk_count: 48, error: null })).toBe(
      "48 Fragmentos · indexado",
    );
    expect(documentDetail({ status: "indexing", chunk_count: 0, error: null })).toBe("Indexando…");
    expect(
      documentDetail({ status: "failed", chunk_count: 0, error: "Formato não suportado." }),
    ).toBe("Falhou: Formato não suportado.");
  });
});
