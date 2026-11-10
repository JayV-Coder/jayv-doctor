import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

test("Owner cadastra o webhook do ITSM: metadados recusados, segredo mostrado uma vez", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await ownerWithOrganization(page, `Webhooks ${randomUUID().slice(0, 8)}`);
  await page.goto("/mais");
  await page.getByRole("link", { name: "Webhooks" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Webhooks" })).toBeVisible();
  await expect(page.getByText("Nenhum webhook")).toBeVisible();

  await page.getByRole("button", { name: "Novo webhook" }).click();
  const sheet = page.getByRole("dialog", { name: "Novo webhook" });
  await sheet.getByLabel("Nome").fill("ITSM");
  // Critério do #42: o endereço de metadados é recusado no cadastro.
  await sheet.getByLabel("Endereço (HTTPS)").fill("https://169.254.169.254/latest/meta-data");
  await sheet.getByRole("button", { name: "Criar webhook" }).click();
  await expect(sheet.getByRole("alert")).toContainText("IP privado, local ou de metadados");

  await sheet.getByLabel("Endereço (HTTPS)").fill("https://example.com/aid-webhook");
  await sheet.getByLabel("Incidente resolvido").check();
  await expectNoHorizontalScroll(page);
  await sheet.getByRole("button", { name: "Criar webhook" }).click();
  await expect(sheet.getByRole("status")).toContainText("não aparece de novo");
  await expect(sheet.locator(".cmd code")).toContainText("whsec_");
  await page.keyboard.press("Escape");

  const card = page.getByRole("article", { name: "ITSM" });
  await expect(card).toContainText("Incidente aberto, Incidente resolvido");
  await expect(card).toContainText("Ativo");
  await expect(page.locator(".cmd")).toHaveCount(0);
  await card.getByRole("switch").uncheck();
  await page.reload();
  await expect(page.getByRole("article", { name: "ITSM" })).toContainText("Desligado");
  await expectNoHorizontalScroll(page);
});
