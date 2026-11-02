import { describe, expect, it } from "vitest";
import { environmentLabel, environmentTone, errorRateText, flowLabel } from "./labels";

describe("Ambiente", () => {
  it("usa os nomes do glossário", () => {
    expect(environmentLabel("prd")).toBe("Produção");
    expect(environmentLabel("hml")).toBe("Homologação");
    expect(environmentLabel("dev")).toBe("Desenvolvimento");
  });

  it("destaca produção, como no mockup", () => {
    expect(environmentTone("prd")).toBe("danger");
    expect(environmentTone("hml")).toBe("info");
    expect(environmentTone("dev")).toBe("neutral");
  });
});

describe("flowLabel", () => {
  it("mostra origem → destino pelos nomes dos sistemas", () => {
    expect(flowLabel("salesforce", "sap")).toBe("Salesforce → SAP");
    expect(flowLabel("gcp", "other")).toBe("Google Cloud → Outro");
  });
});

describe("errorRateText", () => {
  it("sem Execuções não inventa 0%", () => {
    expect(errorRateText(null)).toBe("sem Execuções");
  });

  it("formata a taxa em pt-BR", () => {
    expect(errorRateText(0.041)).toBe("4,1%");
  });
});
