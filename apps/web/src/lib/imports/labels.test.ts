import { describe, expect, it } from "vitest";
import { importSummary, statusLabel, statusTone } from "./labels";

describe("status da Importação", () => {
  it("fala a língua do mockup", () => {
    expect(statusLabel("pending")).toBe("Enviando");
    expect(statusLabel("uploaded")).toBe("Na fila");
    expect(statusLabel("processing")).toBe("Normalizando");
    expect(statusLabel("done")).toBe("Concluída");
    expect(statusLabel("failed")).toBe("Falhou");
    expect(statusLabel("rejected")).toBe("Recusada");
  });

  it("marca recusa e falha como problema e conclusão como sucesso", () => {
    expect(statusTone("rejected")).toBe("danger");
    expect(statusTone("failed")).toBe("danger");
    expect(statusTone("done")).toBe("success");
    expect(statusTone("processing")).toBe("info");
  });
});

describe("importSummary", () => {
  it("resume eventos, rejeições, duplicados e segredos removidos", () => {
    expect(importSummary({ accepted: 2004, rejected: 14, duplicates: 0, secrets_removed: 3 })).toBe(
      "2.004 eventos · 14 rejeitadas · 3 segredos removidos",
    );
  });

  it("omite o que é zero", () => {
    expect(importSummary({ accepted: 1, rejected: 0, duplicates: 0, secrets_removed: 0 })).toBe(
      "1 evento",
    );
  });
});
