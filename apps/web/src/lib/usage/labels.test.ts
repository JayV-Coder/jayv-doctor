import { describe, expect, it } from "vitest";
import { amountText, quotaWarning, resourceLabel } from "./labels";

describe("Uso e cotas", () => {
  it("nomes e quantidades", () => {
    expect(resourceLabel("diagnoses_llm")).toBe("Diagnósticos com IA");
    expect(amountText("events_ingested", 2_400_000)).toBe("2,4 mi");
    expect(amountText("storage_bytes", 18_000_000_000)).toBe("18 GB");
    expect(amountText("members", 12)).toBe("12");
  });

  it("aviso aos 80% e aos 100%", () => {
    expect(quotaWarning("diagnoses_llm", 0.91)).toBe("91% — depois disso, só Regras");
    expect(quotaWarning("diagnoses_llm", 1)).toBe(
      "Cota de IA esgotada: novos Diagnósticos rodam só com as Regras",
    );
    expect(quotaWarning("events_ingested", 1.05)).toBe(
      "Cota esgotada: a ingestão é recusada acima de 110%",
    );
    expect(quotaWarning("members", 1)).toBe("Limite do plano atingido: novos itens são bloqueados");
    expect(quotaWarning("events_ingested", 0.5)).toBeNull();
  });
});
