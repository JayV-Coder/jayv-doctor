import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createIntegration, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

test("Owner mapeia a chave do pedido entre Salesforce, middleware e SAP", async ({ page }) => {
  test.setTimeout(120_000);
  await ownerWithOrganization(page, `Mapas ${randomUUID().slice(0, 8)}`);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  const card = page.getByRole("article", { name: "Pedidos Salesforce → SAP" });
  await card.getByRole("link", { name: "Mapa entre sistemas" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Mapa entre sistemas" })).toBeVisible();
  await expect(page.getByText("Nenhum mapa")).toBeVisible();

  await page.getByRole("button", { name: "Novo mapa" }).click();
  const sheet = page.getByRole("dialog", { name: "Novo mapa" });
  await sheet.getByLabel("Nome").fill("Pedido de venda");
  const fields = sheet.getByLabel("Campo do Evento");
  await fields.nth(0).fill("execution_id");
  await fields.nth(1).fill("attributes.sf_order");
  await sheet.getByLabel("Tirar o prefixo").nth(1).fill("SF-");
  await fields.nth(2).fill("attributes.bstkd");
  await sheet.getByLabel("Tirar zeros à esquerda").nth(2).check();
  await sheet.getByLabel(/Avisar quando a origem não chegar/).check();
  await expectNoHorizontalScroll(page);
  await sheet.getByRole("button", { name: "Salvar mapa" }).click();

  const mapping = page.getByRole("article", { name: "Pedido de venda" });
  await expect(mapping).toContainText("Google Cloud · attributes.sf_order (sem o prefixo SF-)");
  await expect(mapping).toContainText("SAP · attributes.bstkd (sem zeros à esquerda)");
  await expect(mapping).toContainText("divergência");
  await expectNoHorizontalScroll(page);

  // Campo fora da regra: a API diz qual item e qual regra.
  await page.getByRole("button", { name: "Novo mapa" }).click();
  await sheet.getByLabel("Nome").fill("Ruim");
  await sheet.getByLabel("Campo do Evento").nth(0).fill("payload.inteiro");
  await sheet.getByRole("button", { name: "Salvar mapa" }).click();
  await expect(sheet.getByRole("alert")).toContainText("keys[0].field");
  await page.keyboard.press("Escape");

  await mapping.getByRole("button", { name: "Remover Pedido de venda" }).click();
  await page.getByRole("button", { name: "Confirmar remoção de Pedido de venda" }).click();
  await expect(page.getByText("Nenhum mapa")).toBeVisible();
});
