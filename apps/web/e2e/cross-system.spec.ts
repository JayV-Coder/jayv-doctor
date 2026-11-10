import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createIntegration, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

// Salesforce → Cloud Run → timeout no SAP, ligados pelo Mapa de identificadores (#40).
function seed(organization: string, integration: string): string {
  return execFileSync(
    "uv",
    ["run", "python", "apps/web/e2e/seed_cross_system.py", organization, integration],
    { cwd: "../..", encoding: "utf8" },
  ).trim();
}

test("a Timeline mostra as 3 raias numa única Execução", async ({ page }) => {
  test.setTimeout(120_000);
  const organization = `Raias ${randomUUID().slice(0, 8)}`;
  await ownerWithOrganization(page, organization);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  const execution = seed(organization, "Pedidos Salesforce → SAP");

  await page.goto(`/execucoes/${execution}`);
  await expect(page.getByRole("heading", { name: "3 eventos correlacionados" })).toBeVisible();
  await expect(page.getByText("801XX0001", { exact: true })).toBeVisible();
  const timeline = page.getByRole("list", {
    name: "Timeline em raias: Salesforce, Google Cloud, SAP",
  });
  await expect(timeline.getByRole("link")).toHaveCount(3);
  await expect(timeline.getByRole("link").nth(0)).toContainText("Salesforce ·");
  await expect(timeline.getByRole("link").nth(1)).toContainText("Google Cloud ·");
  await expect(timeline.getByRole("link").nth(2)).toContainText("SAP ·");
  await expect(timeline.getByRole("link").nth(2)).toContainText("INT-003");
  await expectNoHorizontalScroll(page);
});
