import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import {
  createIntegration,
  enrollFactor,
  expectNoHorizontalScroll,
  fillOrganization,
  fillOtp,
  signInWithPassword,
  signUp,
  totp,
  uniqueEmail,
} from "./helpers";

// A mesma da API do E2E (playwright.config.ts).
const E2E_HMAC_KEY = "chave-mestre-local-do-e2e-nao-usar-em-producao";

function state(page: Page, name: string) {
  return page.getByRole("article", { name: `Estado ${name}`, exact: true });
}

test("estados do card de Diagnóstico", async ({ page }) => {
  const email = uniqueEmail();
  await signUp(email);
  await signInWithPassword(page, email);
  await expect(page).toHaveURL(/\/organizacoes\/nova/);
  await page.goto("/componentes/diagnostico");
  await expect(
    page.getByRole("heading", { level: 1, name: "Estados do Diagnóstico" }),
  ).toBeVisible();

  await expect(state(page, "queued")).toContainText("Na fila…");
  const running = state(page, "running");
  await expect(running.getByRole("status")).toHaveText("Interpretando…");
  await expect(running.locator('[aria-current="step"]')).toHaveText("Interpretando");
  await expect(running.getByRole("list", { name: "Evidências do Diagnóstico" })).toHaveCount(0);

  const published = state(page, "published");
  await expect(published).toContainText("Requer revisão");
  await expect(published).toContainText("Causa provável");
  await expect(published).toContainText("Confiança heurística (não calibrada)");
  await expect(published).toContainText("0,68");
  await expect(published).toContainText("Indeterminado");
  // Recomendações numeradas, sem botão de execução.
  await expect(published.getByRole("list", { name: "Recomendações" })).toBeVisible();
  await expect(published.getByRole("button", { name: /Executar/ })).toHaveCount(0);
  await expect(published.getByRole("link", { name: /INT-003/ })).toHaveAttribute(
    "href",
    "/eventos/00000000-0000-4000-8000-000000000701",
  );

  const inconclusive = state(page, "inconclusive");
  await expect(inconclusive).toContainText("Inconclusivo");
  await expect(inconclusive).toContainText("Evidências insuficientes");
  await expect(inconclusive).not.toContainText("Causa provável");

  await expect(state(page, "failed_llm")).toContainText("O modelo de IA falhou");
  await expect(state(page, "failed")).toContainText("Incidente não encontrado.");
  await expectNoHorizontalScroll(page);
});

test("pede o Diagnóstico, acompanha, compara versões e o Viewer só lê", async ({ page }) => {
  test.setTimeout(180_000);
  const organization = `Diagnóstico ${randomUUID().slice(0, 8)}`;
  const email = uniqueEmail();
  await signUp(email);
  await signInWithPassword(page, email);
  await fillOrganization(page, organization);
  const secret = await enrollFactor(page);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("article", { name: "Pedidos Salesforce → SAP" })).toBeVisible();
  execFileSync(
    "uv",
    ["run", "python", "apps/web/e2e/seed_execution.py", organization, "Pedidos Salesforce → SAP"],
    { cwd: "../..", env: { ...process.env, HMAC_MASTER_KEY: E2E_HMAC_KEY } },
  );
  const worker = (...args: string[]) => {
    execFileSync("uv", ["run", "python", "apps/web/e2e/seed_diagnosis.py", organization, ...args], {
      cwd: "../..",
    });
  };

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/incidentes");
  await page.getByRole("link", { name: /INC-0001 Timeout/ }).click();
  await expect(page.getByRole("region", { name: "Diagnóstico", exact: true })).toContainText(
    "Ainda não há Diagnóstico",
  );

  // v1: só Regras.
  await page.getByRole("button", { name: "Novo diagnóstico" }).click();
  await page.getByLabel("Só Regras (sem IA)").check();
  await page.getByRole("button", { name: "Diagnosticar" }).click();
  const card = page.getByRole("region", { name: "Diagnóstico", exact: true });
  await expect(card).toContainText("diagnóstico v1 · só Regras");
  await expect(card).toContainText("Na fila…");
  worker();
  await expect(card).toContainText("Requer revisão", { timeout: 15_000 });
  await expect(card).toContainText("Causa provável");
  await expect(card).toContainText("Confiança heurística (não calibrada)");
  await expectNoHorizontalScroll(page);

  // Da Evidência ao JSON do Evento: 1 toque.
  await page
    .getByRole("list", { name: "Evidências do Diagnóstico" })
    .getByRole("link")
    .nth(1)
    .click();
  await expect(page.getByRole("heading", { name: "Evento original" })).toBeVisible();
  await page.goBack();

  // v2: híbrido; o modelo não acha Evidência e o resultado é inconclusivo.
  await page.getByRole("button", { name: "Novo diagnóstico" }).click();
  await page.getByRole("button", { name: "Diagnosticar" }).click();
  await expect(card).toContainText("diagnóstico v2 · híbrido");
  worker();
  await expect(card).toContainText("Evidências insuficientes", { timeout: 15_000 });
  await expect(card).not.toContainText("Causa provável");
  const versions = page.getByRole("navigation", { name: "Versões do Diagnóstico" });
  await expect(versions.getByRole("link")).toHaveCount(2);
  await expect(page.getByRole("region", { name: "Diferenças entre versões" })).toContainText(
    "Status: Publicado → Inconclusivo",
  );
  await versions.getByRole("link", { name: /v1/ }).click();
  await expect(page).toHaveURL(/versao=1/);
  await expect(card).toContainText("diagnóstico v1 · só Regras");

  // Desktop: Diagnóstico à esquerda, Evidências à direita.
  await page.setViewportSize({ width: 1280, height: 900 });
  const left = await card.boundingBox();
  const right = await page.getByRole("list", { name: "Evidências do Diagnóstico" }).boundingBox();
  expect(left && right && right.x > left.x + left.width - 1).toBe(true);
  await expect(page.getByRole("region", { name: "Hipóteses do Diagnóstico" })).toHaveCount(0);
  await page.goto(page.url().replace("versao=1", "versao=2"));
  await expect(page.getByRole("region", { name: "Hipóteses do Diagnóstico" })).toBeVisible();

  // Viewer: lê, mas não vê "Novo diagnóstico".
  worker("viewer");
  const incident = page.url();
  await page.context().clearCookies();
  await signInWithPassword(page, email);
  await fillOtp(page, totp(secret));
  await page.getByRole("button", { name: "Verificar" }).click();
  await expect(page).not.toHaveURL(/\/(login|mfa)/);
  await page.goto(incident);
  await expect(card).toContainText("Evidências insuficientes");
  await expect(page.getByRole("button", { name: "Novo diagnóstico" })).toHaveCount(0);
});
