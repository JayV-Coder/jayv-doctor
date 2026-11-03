import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createIntegration, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

// A mesma da API do E2E (playwright.config.ts).
const E2E_HMAC_KEY = "chave-mestre-local-do-e2e-nao-usar-em-producao";

test("Dashboard mostra o Incidente crítico, os KPIs e as falhas por categoria", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const organization = `Painel ${randomUUID().slice(0, 8)}`;
  await ownerWithOrganization(page, organization);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("article", { name: "Pedidos Salesforce → SAP" })).toBeVisible();
  execFileSync(
    "uv",
    ["run", "python", "apps/web/e2e/seed_execution.py", organization, "Pedidos Salesforce → SAP"],
    { cwd: "../..", env: { ...process.env, HMAC_MASTER_KEY: E2E_HMAC_KEY } },
  );

  await page.goto("/");
  await expect(page.getByRole("link", { name: /INC-0001/ })).toContainText("Crítico");
  const kpis = page.locator(".kpis");
  await expect(kpis).toContainText("Execuções1");
  await expect(kpis).toContainText("Taxa de erro100%");
  await expect(kpis).toContainText("Incidentes abertos1");
  await expect(page.getByRole("list", { name: "Falhas por categoria" })).toContainText("Timeout");
  await expect(page.getByRole("img", { name: /Falhas por hora, pico de 1/ })).toBeVisible();
  await expectNoHorizontalScroll(page);

  await page.getByRole("link", { name: "7 dias" }).click();
  await expect(page).toHaveURL(/periodo=7d/);
  await expect(page.getByRole("img", { name: /Falhas por dia/ })).toBeVisible();
  await page.getByRole("link", { name: "Homologação" }).click();
  await expect(page).toHaveURL(/ambiente=hml/);
  await expect(kpis).toContainText("Execuções0");
  await expect(kpis).toContainText("sem Execuções");
});
