import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createIntegration, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

const ORDER = "4500012345";
// A mesma da API do E2E (playwright.config.ts): o HMAC da semente e o da busca batem.
const E2E_HMAC_KEY = "chave-mestre-local-do-e2e-nao-usar-em-producao";

// Os 6 Eventos da Tela 8, correlacionados, fechados e avaliados pelos módulos dos workers.
function seed(organization: string, integration: string): string {
  return execFileSync(
    "uv",
    ["run", "python", "apps/web/e2e/seed_execution.py", organization, integration],
    {
      cwd: "../..",
      encoding: "utf8",
      env: { ...process.env, HMAC_MASTER_KEY: process.env.HMAC_MASTER_KEY ?? E2E_HMAC_KEY },
    },
  ).trim();
}

test("busca por trace e por nº do pedido, abre a Timeline e chega ao Evento original", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const organization = `Explora ${randomUUID().slice(0, 8)}`;
  await ownerWithOrganization(page, organization);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("article", { name: "Pedidos Salesforce → SAP" })).toBeVisible();
  seed(organization, "Pedidos Salesforce → SAP");

  await page.goto("/execucoes");
  const list = page.getByRole("list", { name: "Execuções" });
  await expect(list.getByRole("link", { name: /exec-123 · trace-abc/ })).toBeVisible();
  await expect(list).toContainText("Falhou");
  await expect(list).toContainText("Incidente");
  await expectNoHorizontalScroll(page);

  // Busca por trace e pelo nº do pedido: o número não vai para a URL.
  const search = page.getByRole("searchbox", { name: "Buscar Execução" });
  await search.fill("trace-zzz");
  await page.getByRole("button", { name: "Buscar" }).click();
  await expect(page.getByText("Nenhuma Execução para essa busca.")).toBeVisible();
  await search.fill(ORDER);
  await page.getByRole("button", { name: "Buscar" }).click();
  await expect(list.getByRole("link", { name: /exec-123/ })).toBeVisible();
  expect(page.url()).not.toContain(ORDER);

  // Filtro rápido na URL.
  await page.getByRole("link", { name: "Falhas" }).click();
  await expect(page).toHaveURL(/status=failed/);
  await expect(list.getByRole("link", { name: /exec-123/ })).toBeVisible();

  // Incidente → Timeline → Evento: a Timeline mostra os 6 e a prova da Regra.
  await list.getByRole("link", { name: /exec-123/ }).click();
  await expect(page.getByRole("heading", { level: 2, name: "exec-123 · trace-abc" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "6 eventos correlacionados" })).toBeVisible();
  const timeline = page.getByRole("list", { name: "Timeline" });
  await expect(timeline.getByRole("link")).toHaveCount(6);
  const flagged = timeline.getByRole("link", { name: /HTTP 504 TIMEOUT/ });
  await expect(flagged).toContainText("INT-003");
  await expect(timeline).toContainText("por trace_id");
  await expectNoHorizontalScroll(page);

  await flagged.click();
  await expect(page.getByRole("heading", { level: 1, name: "Evento original" })).toBeVisible();
  const json = page.getByRole("region", { name: "Evento normalizado" });
  await expect(json).toContainText('"http_status": 504');
  await expect(json).toContainText("[REMOVIDO:bearer]");
  await expect(page.getByRole("region", { name: "Sanitização aplicada" })).toContainText(
    "1 token Bearer removido",
  );
  await page.getByRole("tab", { name: "Log bruto" }).click();
  await expect(
    page.getByRole("button", { name: "Baixar Log bruto (link de 5 min)" }),
  ).toBeVisible();
  await expectNoHorizontalScroll(page);
});
