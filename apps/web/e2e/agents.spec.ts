import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createIntegration, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

test("Owner cadastra um agente, vê o comando de instalação uma vez e revoga", async ({ page }) => {
  test.setTimeout(120_000);
  await ownerWithOrganization(page, `Agentes ${randomUUID().slice(0, 8)}`);
  await page.goto("/integracoes");
  await createIntegration(page, "IDocs SAP → GCP");

  await page.goto("/conectores");
  await page.getByRole("link", { name: "Ver agentes" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Agentes locais" })).toBeVisible();
  await expect(page.getByText("Nenhum agente instalado")).toBeVisible();
  await page.getByRole("link", { name: "Adicionar" }).click();

  await page.getByLabel("Nome do agente").fill("SAP ECC Campinas");
  await page.getByLabel("Pasta de exportações (SM58, SLG1, IDocs)").fill("/exports/sap");
  await page.getByLabel("Status de IDoc via RFC (tabela EDIDS)").check();
  await page.getByRole("button", { name: "Gerar token" }).click();
  const command = page.locator(".cmd code");
  await expect(command).toContainText("--token aid_reg_");
  await expect(page.getByText("não aparece de novo")).toBeVisible();
  await expectNoHorizontalScroll(page);

  await page.getByRole("link", { name: "Ver agentes" }).click();
  const card = page.getByRole("article", { name: "SAP ECC Campinas" });
  await expect(card.getByText("Aguardando registro")).toBeVisible();
  await expect(card.getByText("pasta /exports/sap · tabela EDIDS")).toBeVisible();
  // O token não aparece de novo na lista.
  await expect(page.locator(".cmd")).toHaveCount(0);
  await expectNoHorizontalScroll(page);

  await card.getByRole("button", { name: "Revogar SAP ECC Campinas" }).click();
  await card.getByRole("button", { name: "Confirmar revogação de SAP ECC Campinas" }).click();
  await expect(card.getByText("Revogado")).toBeVisible();
  await expect(card.getByRole("button")).toHaveCount(0);
});
