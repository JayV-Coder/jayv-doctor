import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import { createIntegration, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

const NDJSON = Buffer.from(
  '{"timestamp":"2026-11-02T14:05:00Z","operation":"BAPI_SALESORDER","severity":"error"}\n',
);

async function upload(page: Page, name: string, buffer: Buffer): Promise<void> {
  await page.getByLabel("Escolher arquivo").setInputFiles({
    name,
    mimeType: "application/octet-stream",
    buffer,
  });
}

function card(page: Page, name: string) {
  return page.getByRole("article", { name }).first();
}

test("importa NDJSON, recusa formato errado e marca o arquivo repetido", async ({ page }) => {
  await ownerWithOrganization(page, `Importa ${randomUUID().slice(0, 8)}`);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("article", { name: "Pedidos Salesforce → SAP" })).toBeVisible();

  await page.goto("/conectores");
  await page.getByRole("link", { name: "Importar logs" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Importar logs" })).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Navegação principal" });
  await expect(nav.getByRole("link", { name: "Conectores" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expectNoHorizontalScroll(page);

  await upload(page, "sap-orders.ndjson", NDJSON);
  await expect(card(page, "sap-orders.ndjson")).toContainText("Na fila");

  await upload(page, "export-old.xml", Buffer.from("<pedidos/>"));
  await expect(card(page, "export-old.xml")).toContainText("Recusada");
  await expect(card(page, "export-old.xml")).toContainText("Formato não permitido");

  await upload(
    page,
    "imagem.csv",
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0]),
  );
  await expect(card(page, "imagem.csv")).toContainText("Conteúdo não corresponde ao formato");

  await upload(page, "copia.ndjson", NDJSON);
  await expect(card(page, "copia.ndjson")).toContainText("Arquivo já importado nesta Integração");
  await expectNoHorizontalScroll(page);
});
