import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

test("Tela 21: Jira, ServiceNow e o webhook genérico; sem app do Jira, avisa", async ({ page }) => {
  test.setTimeout(120_000);
  await ownerWithOrganization(page, `ITSM ${randomUUID().slice(0, 8)}`);
  await page.goto("/mais");
  await page.getByRole("link", { name: "Chamados (ITSM)" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Chamados (ITSM)" })).toBeVisible();
  const jira = page.getByRole("region", { name: "Jira Service Management" });
  await expect(jira).toContainText("Não conectado");
  const servicenow = page.getByRole("region", { name: "ServiceNow" });
  await expect(servicenow).toContainText("Não conectado");
  await expect(page.getByRole("region", { name: "Webhook genérico" })).toContainText("0 ativo(s)");
  await expectNoHorizontalScroll(page);
  // O E2E não tem o app OAuth do Atlassian: a tela diz isso em vez de quebrar.
  await jira.getByRole("button", { name: "Conectar Jira" }).click();
  await expect(jira.getByRole("alert")).toContainText(
    "O app do Jira não está configurado na plataforma.",
  );
  await page.goto("/chamados?jira=erro");
  await expect(page.getByRole("alert").first()).toContainText("O Jira não foi conectado.");

  // ServiceNow (#44): credenciais no Vault; o endereço da Business Rule aparece uma vez.
  await page.goto("/chamados");
  await servicenow.getByLabel("Instância").fill("https://acme.service-now.com");
  await servicenow.getByLabel("Client ID").fill("app-doctor");
  await servicenow.getByLabel("Client secret").fill("segredo-da-instancia");
  await servicenow.getByLabel("SAP").fill("SAP Basis");
  await servicenow.getByLabel("Grupo padrão (Indeterminado)").fill("Service Desk");
  await servicenow.getByRole("button", { name: "Conectar ServiceNow" }).click();
  await expect(servicenow.getByRole("status")).toContainText("Guarde o endereço agora");
  await expect(servicenow.locator("code")).toContainText("/api/v1/itsm/servicenow/hooks/");
  await expectNoHorizontalScroll(page);
  await page.reload();
  await expect(servicenow).toContainText("Conectado");
  await expect(servicenow).toContainText("acme.service-now.com");
  await expect(servicenow.getByLabel("SAP")).toHaveValue("SAP Basis");
  await expect(servicenow.locator("code")).toHaveCount(0);
});
