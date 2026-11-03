import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createIntegration, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

// A mesma da API do E2E (playwright.config.ts).
const E2E_HMAC_KEY = "chave-mestre-local-do-e2e-nao-usar-em-producao";

test("lista com contagem, muda status, comenta e resolve com nota", async ({ page }) => {
  test.setTimeout(120_000);
  const organization = `Incidente ${randomUUID().slice(0, 8)}`;
  await ownerWithOrganization(page, organization);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("article", { name: "Pedidos Salesforce → SAP" })).toBeVisible();
  // Os 6 Eventos da Tela 8: o 504 abre um Incidente TIMEOUT pelas Regras de verdade.
  execFileSync(
    "uv",
    ["run", "python", "apps/web/e2e/seed_execution.py", organization, "Pedidos Salesforce → SAP"],
    { cwd: "../..", env: { ...process.env, HMAC_MASTER_KEY: E2E_HMAC_KEY } },
  );

  await page.goto("/incidentes");
  await expect(page.getByRole("link", { name: "Abertos 1" })).toBeVisible();
  const card = page.getByRole("link", { name: /INC-0001 Timeout/ });
  await expect(card).toContainText("Crítico");
  await expect(card).toContainText("TIMEOUT · INT-003");
  await expectNoHorizontalScroll(page);

  // Busca pelo número e pelo nº do pedido, sem levar o termo para a URL.
  const search = page.getByRole("searchbox", { name: "Buscar Incidente" });
  await search.fill("4500012345");
  await page.getByRole("button", { name: "Buscar" }).click();
  await expect(card).toBeVisible();
  expect(page.url()).not.toContain("4500012345");

  await card.click();
  await expect(page.getByRole("heading", { level: 2, name: /INC-0001 · Timeout/ })).toBeVisible();
  await expect(page.getByRole("list", { name: "Evidências" })).toContainText("INT-003");
  await expect(page.getByRole("list", { name: "Execuções vinculadas" })).toContainText("exec-123");

  await page.getByLabel("Mudar status").selectOption("investigating");
  await page.getByRole("button", { name: "Salvar status" }).click();
  await expect(page.getByRole("list", { name: "Histórico" })).toContainText("Aberto → Em análise");

  await page.getByRole("button", { name: "Assumir" }).click();
  await expect(page.getByRole("button", { name: "Liberar" })).toBeVisible();

  await page.getByLabel("Comentário").fill("Gateway do SAP com timeout de 30 s.");
  await page.getByRole("button", { name: "Comentar" }).click();
  await expect(page.getByRole("list", { name: "Comentários" })).toContainText(
    "Gateway do SAP com timeout de 30 s.",
  );

  await page.getByLabel("Mudar status").selectOption("resolved");
  await expect(page.getByRole("button", { name: "Salvar status" })).toBeDisabled();
  await page.getByLabel("Nota de resolução").fill("Timeout do gateway ajustado para 60 s.");
  await page.getByRole("button", { name: "Salvar status" }).click();
  await expect(page.getByText("Resolução: Timeout do gateway ajustado para 60 s.")).toBeVisible();
  await expectNoHorizontalScroll(page);

  // Do Incidente ao Evento original: Evidência → Evento.
  await page.getByRole("list", { name: "Evidências" }).getByRole("link").first().click();
  await expect(page.getByRole("heading", { level: 1, name: "Evento original" })).toBeVisible();
});
