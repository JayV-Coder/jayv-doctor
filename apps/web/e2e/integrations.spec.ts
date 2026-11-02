import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createIntegration, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test("o onboarding termina sugerindo a primeira Integração", async ({ page }) => {
  await ownerWithOrganization(page, `Primeira ${randomUUID().slice(0, 8)}`);
  await page.goto("/");
  await page.getByRole("link", { name: "Cadastrar Integração" }).click();
  await expect(page).toHaveURL(/\/integracoes$/);
  await expect(page.getByRole("heading", { level: 1, name: "Integrações" })).toBeVisible();
});

test("Owner cadastra, recebe erro na repetida e arquiva", async ({ page }) => {
  await ownerWithOrganization(page, `Integra ${randomUUID().slice(0, 8)}`);
  await page.goto("/mais");
  await page.getByRole("link", { name: "Integrações" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Integrações" })).toBeVisible();

  await createIntegration(page, "Pedidos Salesforce → SAP");
  const card = page.getByRole("article", { name: "Pedidos Salesforce → SAP" });
  await expect(card).toBeVisible();
  await expect(card).toContainText("Produção");
  await expect(card).toContainText("Salesforce → SAP");
  await expect(card).toContainText("sem Execuções");
  await expectNoHorizontalScroll(page);

  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("dialog", { name: "Nova integração" }).getByRole("alert")).toHaveText(
    "Já existe uma Integração com este nome neste Ambiente.",
  );
  await page
    .getByRole("dialog", { name: "Nova integração" })
    .getByRole("button", { name: "Fechar" })
    .click();

  await card.getByRole("button", { name: "Arquivar" }).click();
  const confirm = page.getByRole("dialog", { name: "Arquivar integração" });
  await confirm.getByRole("button", { name: "Arquivar Pedidos Salesforce → SAP" }).click();
  await expect(card).toHaveCount(0);
  await expect(page.getByText("Nenhuma Integração cadastrada")).toBeVisible();

  // Arquivar libera o nome para um novo cadastro.
  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("article", { name: "Pedidos Salesforce → SAP" })).toBeVisible();
});
