import { describe, expect, it } from "vitest";
import { keysFromForm, keySummary, lookupFromForm } from "./form";

function form(entries: Record<string, string>): FormData {
  const data = new FormData();
  for (const [name, value] of Object.entries(entries)) data.set(name, value);
  return data;
}

describe("Mapa de identificadores na tela", () => {
  it("cada linha preenchida vira uma chave, com as transformações marcadas", () => {
    const keys = keysFromForm(
      form({
        "system-0": "salesforce",
        "field-0": "execution_id",
        "system-1": "gcp",
        "field-1": "attributes.sf_order",
        "prefix-1": "SF-",
        "system-2": "sap",
        "field-2": " attributes.bstkd ",
        "zeros-2": "on",
        "upper-2": "on",
      }),
    );
    expect(keys).toEqual([
      { system: "salesforce", field: "execution_id", transforms: [{ op: "trim" }] },
      {
        system: "gcp",
        field: "attributes.sf_order",
        transforms: [{ op: "trim" }, { op: "strip_prefix", value: "SF-" }],
      },
      {
        system: "sap",
        field: "attributes.bstkd",
        transforms: [{ op: "trim" }, { op: "strip_leading_zeros" }, { op: "upper" }],
      },
    ]);
  });

  it("linha sem campo fica de fora", () => {
    expect(keysFromForm(form({ "system-0": "sap", "field-0": "" }))).toEqual([]);
  });

  it("consulta só com Conector escolhido", () => {
    expect(lookupFromForm(form({ connector: "" }))).toBeNull();
    expect(
      lookupFromForm(
        form({
          connector: "c1",
          entity: "A_SalesOrder",
          "lookup-field": "PurchaseOrderByCustomer",
          pad: "10",
        }),
      ),
    ).toEqual({
      connector_id: "c1",
      entity: "A_SalesOrder",
      field: "PurchaseOrderByCustomer",
      status_field: null,
      pad_left: 10,
    });
  });

  it("resumo legível das chaves", () => {
    expect(
      keySummary({
        system: "gcp",
        field: "attributes.sf_order",
        transforms: [{ op: "trim" }, { op: "strip_prefix", value: "SF-" }],
      }),
    ).toBe("Google Cloud · attributes.sf_order (sem o prefixo SF-)");
  });
});
