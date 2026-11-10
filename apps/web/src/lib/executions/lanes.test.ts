import { describe, expect, it } from "vitest";
import { crossKeysText, laneOf, lanes } from "./lanes";

const at = (provider: string) => ({ source: { provider, service: "s" } });

describe("raias por sistema", () => {
  it("uma raia por sistema, na ordem do fluxo", () => {
    const events = [at("sap"), at("salesforce"), at("gcp"), at("sap")];
    expect(lanes(events)).toEqual([
      { system: "salesforce", label: "Salesforce", short: "SF" },
      { system: "gcp", label: "Google Cloud", short: "GCP" },
      { system: "sap", label: "SAP", short: "SAP" },
    ]);
  });
  it("sistema fora da lista conhecida vai para o fim, pelo nome", () => {
    expect(lanes([at("mulesoft"), at("salesforce")]).map((lane) => lane.system)).toEqual([
      "salesforce",
      "mulesoft",
    ]);
  });
  it("Evento sem provedor fica na raia 'outros'", () => {
    expect(laneOf({ source: {} })).toBe("custom");
    expect(lanes([{ source: {} }])[0]?.label).toBe("Outros");
  });
});

describe("chaves entre sistemas", () => {
  it("mostra só os valores, sem o id do Mapa", () => {
    expect(crossKeysText(["m1:801XX0001", "m2:801XX0001", "m2:IDOC-77"])).toBe(
      "801XX0001, IDOC-77",
    );
  });
});
