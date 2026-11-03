import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createIntegration, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

// A mesma da API do E2E (playwright.config.ts).
const E2E_HMAC_KEY = "chave-mestre-local-do-e2e-nao-usar-em-producao";

test("Cota de IA esgotada: a Tela 17 avisa e o Diagnóstico roda só com as Regras", async ({
  page,
}) => {
  test.setTimeout(150_000);
  const organization = `Cotas ${randomUUID().slice(0, 8)}`;
  await ownerWithOrganization(page, organization);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("article", { name: "Pedidos Salesforce → SAP" })).toBeVisible();
  const python = (script: string, ...args: string[]) => {
    execFileSync("uv", ["run", "python", `apps/web/e2e/${script}`, organization, ...args], {
      cwd: "../..",
      env: { ...process.env, HMAC_MASTER_KEY: E2E_HMAC_KEY },
    });
  };
  python("seed_execution.py", "Pedidos Salesforce → SAP");
  python("seed_quota.py");

  await page.goto("/mais");
  await page.getByRole("link", { name: "Uso e cotas" }).click();
  const usage = page.getByRole("list", { name: "Uso por recurso" });
  await expect(usage).toContainText("Diagnósticos com IA");
  await expect(usage).toContainText("1.000/1.000");
  await expect(usage).toContainText(
    "Cota de IA esgotada: novos Diagnósticos rodam só com as Regras",
  );
  await expect(page.getByRole("meter", { name: "Uso de Diagnósticos com IA" })).toHaveAttribute(
    "aria-valuenow",
    "100",
  );
  await expectNoHorizontalScroll(page);

  await page.goto("/incidentes");
  await page.getByRole("link", { name: /INC-0001 Timeout/ }).click();
  await page.getByRole("button", { name: "Novo diagnóstico" }).click();
  await page.getByRole("button", { name: "Diagnosticar" }).click();
  const card = page.getByRole("region", { name: "Diagnóstico", exact: true });
  await expect(card).toContainText("Na fila…");
  python("seed_diagnosis.py");
  await expect(card).toContainText("Cota de IA do mês esgotada: Diagnóstico só com as Regras.", {
    timeout: 15_000,
  });
  await expect(card).toContainText("diagnóstico v1 · só Regras");
});
