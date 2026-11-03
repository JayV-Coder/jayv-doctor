import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createIntegration, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

// A mesma da API do E2E (playwright.config.ts).
const E2E_HMAC_KEY = "chave-mestre-local-do-e2e-nao-usar-em-producao";

test("aceita, corrige, promove à Base e a busca acha o caso", async ({ page }) => {
  test.setTimeout(180_000);
  const organization = `Revisão ${randomUUID().slice(0, 8)}`;
  await ownerWithOrganization(page, organization);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("article", { name: "Pedidos Salesforce → SAP" })).toBeVisible();
  execFileSync(
    "uv",
    ["run", "python", "apps/web/e2e/seed_execution.py", organization, "Pedidos Salesforce → SAP"],
    { cwd: "../..", env: { ...process.env, HMAC_MASTER_KEY: E2E_HMAC_KEY } },
  );
  const run = (script: string) => {
    execFileSync("uv", ["run", "python", `apps/web/e2e/${script}`, organization], {
      cwd: "../..",
    });
  };
  const card = page.getByRole("region", { name: "Diagnóstico", exact: true });
  const review = page.getByRole("region", { name: "Revisão humana" });
  async function diagnoseRulesOnly(version: number) {
    await page.getByRole("button", { name: "Novo diagnóstico" }).click();
    await page.getByLabel("Só Regras (sem IA)").check();
    await page.getByRole("button", { name: "Diagnosticar" }).click();
    await expect(card).toContainText(`diagnóstico v${String(version)} · só Regras`);
    run("seed_diagnosis.py");
    await expect(card).toContainText("Requer revisão", { timeout: 15_000 });
  }

  await page.goto("/incidentes");
  await page.getByRole("link", { name: /INC-0001 Timeout/ }).click();

  await diagnoseRulesOnly(1);
  await review.getByRole("button", { name: "Aceitar" }).click();
  await expect(card).toContainText("Aceito");
  await expect(review).toHaveCount(0);

  await diagnoseRulesOnly(2);
  await review.getByRole("button", { name: "Corrigir" }).click();
  const sheet = page.getByRole("dialog", { name: "Corrigir o Diagnóstico" });
  await sheet.getByLabel("Categoria correta").fill("sap_lock");
  await sheet.getByLabel("Causa correta").fill("Lock na tabela VBAK durante o job noturno.");
  await sheet.getByLabel("Sistema responsável").selectOption("sap");
  await sheet.getByLabel("Comentário").fill("Confirmado com o time SAP.");
  await expectNoHorizontalScroll(page);
  await sheet.getByRole("button", { name: "Salvar correção" }).click();
  await expect(card).toContainText("Corrigido");
  await expect(card).toContainText("Corrigido pela revisão");
  await expect(card).toContainText("SAP_LOCK");
  await expect(card).toContainText("Lock na tabela VBAK durante o job noturno.");
  await expect(page.getByRole("list", { name: "Revisões" })).toContainText(
    "Confirmado com o time SAP.",
  );

  // Resolvido com o Diagnóstico corrigido: o caso vai para a Base.
  await expect(page.getByRole("button", { name: "Promover à Base de conhecimento" })).toHaveCount(
    0,
  );
  await page.getByLabel("Mudar status").selectOption("resolved");
  await page.getByLabel("Nota de resolução").fill("Job noturno remarcado para as 3h.");
  await page.getByRole("button", { name: "Salvar status" }).click();
  await page.getByRole("button", { name: "Promover à Base de conhecimento" }).click();
  await expect(page.getByText("Caso na Base de conhecimento")).toBeVisible();

  run("seed_knowledge.py");
  await page.goto("/conhecimento");
  await expect(page.getByRole("list", { name: "Documentos da organização" })).toContainText(
    "INC-0001",
  );
  await page.getByRole("searchbox").fill("lock VBAK job noturno");
  await page.getByRole("button", { name: "Buscar" }).click();
  await expect(page.getByRole("region", { name: "Resultados da busca" })).toContainText("INC-0001");
});
