import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createIntegration, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

// A mesma da API do E2E (playwright.config.ts).
const E2E_HMAC_KEY = "chave-mestre-local-do-e2e-nao-usar-em-producao";

test("Relatório técnico: gera, baixa, compartilha e revoga o link (Tela 19)", async ({
  page,
  browser,
}) => {
  test.setTimeout(180_000);
  const organization = `Relatório ${randomUUID().slice(0, 8)}`;
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

  await page.goto("/incidentes");
  await page.getByRole("link", { name: /INC-0001 Timeout/ }).click();
  await page.getByRole("button", { name: "Novo diagnóstico" }).click();
  await page.getByRole("radio", { name: "Só Regras (sem IA)" }).check();
  await page.getByRole("button", { name: "Diagnosticar" }).click();
  python("seed_diagnosis.py");
  await expect(page.getByRole("region", { name: "Diagnóstico", exact: true })).toContainText(
    "diagnóstico v1",
    { timeout: 15_000 },
  );

  await page.getByRole("link", { name: "Relatório" }).click();
  const preview = page.getByRole("region", { name: "Pré-visualização" });
  await expect(preview).toContainText("INC-0001");
  await expect(preview).toContainText("Diagnóstico v1");
  await expectNoHorizontalScroll(page);

  // Markdown, para conferir o conteúdo.
  await page.getByLabel("Formato").selectOption("md");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Baixar Markdown" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Gerando o relatório" })).toBeVisible();
  python("seed_report.py");
  const file = readFileSync(await (await download).path(), "utf8");
  expect(file).toContain("# Relatório técnico · ");
  expect(file).toContain("INC-0001 · Timeout");
  expect(file).toContain("## Evidências");
  expect(file).toMatch(/sha256 do texto [0-9a-f]{64}/);
  expect(file).not.toContain("hmac:");

  // Link: abre sem conta, e revogado deixa de abrir.
  await page.getByRole("button", { name: "Compartilhar link" }).click();
  const link = await page.getByLabel("Link compartilhável").inputValue();
  expect(link).toContain("/compartilhado#");
  const guest = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const visitor = await guest.newPage();
  await visitor.goto(link);
  const shared = visitor.waitForEvent("download");
  await visitor.getByRole("button", { name: "Baixar relatório" }).click();
  expect(readFileSync(await (await shared).path(), "utf8")).toContain("INC-0001");

  await page.reload();
  const history = page.getByRole("list", { name: "Relatórios gerados" });
  await expect(history).toContainText("1 acesso(s)");
  await history.getByRole("button", { name: "Revogar" }).click();
  await expect(history.getByRole("button", { name: "Revogar" })).toHaveCount(0);
  await visitor.reload();
  await visitor.getByRole("button", { name: "Baixar relatório" }).click();
  await expect(
    visitor.getByRole("alert").filter({ hasText: "Link inválido, vencido ou revogado." }),
  ).toBeVisible();
  await guest.close();
});
