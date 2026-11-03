import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

const RUNBOOK = Buffer.from(
  "# Runbook de pedidos\n\nQuando a remessa fica bloqueada pelo crédito, o job VL10 para." +
    " Libere o pedido na VKM3 e reprocesse a fila.\n",
);

test("envia um runbook, indexa e encontra pela busca", async ({ page }) => {
  test.setTimeout(120_000);
  const organization = `Conhecimento ${randomUUID().slice(0, 8)}`;
  await ownerWithOrganization(page, organization);

  await page.goto("/mais");
  await page.getByRole("link", { name: "Base de conhecimento" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Conhecimento" })).toBeVisible();
  await expect(page.getByText("Nenhum documento ainda.")).toBeVisible();
  await expectNoHorizontalScroll(page);

  await page.getByRole("button", { name: "Enviar" }).click();
  await page.getByLabel(/Arquivo \(PDF, Markdown/).setInputFiles({
    name: "runbook-pedidos.md",
    mimeType: "text/markdown",
    buffer: RUNBOOK,
  });
  await expect(page.getByText("runbook-pedidos.md enviado.")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.reload();
  const documents = page.getByRole("list", { name: "Documentos da organização" });
  await expect(documents).toContainText("Indexando…");

  execFileSync("uv", ["run", "python", "apps/web/e2e/seed_knowledge.py", organization], {
    cwd: "../..",
  });
  await page.reload();
  await expect(documents).toContainText("1 Fragmento · indexado");

  await page.getByRole("searchbox").fill("remessa bloqueada VL10");
  await page.getByRole("button", { name: "Buscar" }).click();
  const results = page.getByRole("region", { name: "Resultados da busca" });
  await expect(results).toContainText("runbook-pedidos");
  await expect(results).toContainText("Minha organização");
  await expectNoHorizontalScroll(page);

  await page.getByRole("link", { name: /Base global/ }).click();
  await expect(page).toHaveURL(/aba=global/);
  await expect(page.getByRole("list", { name: "Base global" })).toBeVisible();

  await page.goto("/conhecimento");
  await page.getByRole("button", { name: "Remover runbook-pedidos" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remover" }).click();
  await expect(page.getByText("Nenhum documento ainda.")).toBeVisible();
});
