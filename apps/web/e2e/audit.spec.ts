import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { createIntegration, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

test("Owner com MFA vê a trilha, filtra por categoria e termo e exporta o CSV", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const email = await ownerWithOrganization(page, `Auditoria ${randomUUID().slice(0, 8)}`);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("article", { name: "Pedidos Salesforce → SAP" })).toBeVisible();

  await page.goto("/mais");
  await page.getByRole("link", { name: "Auditoria" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Auditoria" })).toBeVisible();
  const trail = page.getByRole("list", { name: "Trilha de auditoria" });
  const chips = page.getByRole("navigation", { name: "Categorias" });
  await expect(trail).toContainText(`${email} criou uma Integração`);
  await expect(trail).toContainText("adicionou um membro");
  await expectNoHorizontalScroll(page);

  await chips.getByRole("link", { name: "Diagnósticos" }).click();
  await expect(page).toHaveURL(/categoria=diagnosis/);
  await expect(page.getByText("Nenhum registro com esses filtros.")).toBeVisible();
  await chips.getByRole("link", { name: "Conectores" }).click();
  await expect(trail).toContainText("criou uma Integração");
  await expect(trail).not.toContainText("adicionou um membro");

  // O termo (aqui, o e-mail) vai no corpo, não na URL.
  await chips.getByRole("link", { name: "Todos" }).click();
  await page.getByRole("searchbox").fill(email);
  await page.getByRole("button", { name: "Buscar" }).click();
  await expect(trail).toContainText("criou uma Integração");
  expect(page.url()).not.toContain(encodeURIComponent(email));

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exportar CSV" }).click();
  const file = await (await download).path();
  const csv = await readFile(file, "utf8");
  expect(csv.split(/\r?\n/)[0]).toBe(
    "occurred_at,actor_type,actor,action,resource_type,resource_id,before,after,ip",
  );
  expect(csv).toContain("integration.created");
});
