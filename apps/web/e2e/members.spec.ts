import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import {
  activeOrganization,
  expectNoHorizontalScroll,
  lastEmailLink,
  lastInvitationLink,
  openEmailLink,
  ownerWithOrganization,
  PASSWORD,
  signUp,
  uniqueEmail,
} from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

async function ownerOnMembers(page: Page, name: string): Promise<void> {
  await ownerWithOrganization(page, name);
  await page.goto("/membros");
}

test("convida, a pessoa entra pelo link e cai na Organização", async ({ page, context }) => {
  const organization = `Acme ${randomUUID().slice(0, 8)}`;
  await ownerOnMembers(page, organization);
  await expectNoHorizontalScroll(page);

  const invited = uniqueEmail();
  await page.getByLabel("E-mail", { exact: true }).fill(invited);
  await page.getByRole("button", { name: "Enviar convite" }).click();
  await expect(page.getByRole("status")).toContainText("Convite enviado");
  await expect(page.getByText(invited, { exact: true })).toBeVisible();
  await expectNoHorizontalScroll(page);

  const link = await lastInvitationLink(invited);
  expect(link).toContain("/convites/aceitar#");
  await context.clearCookies();
  await signUp(invited);

  await page.goto(link);
  await page.getByRole("link", { name: "Entrar para aceitar" }).click();
  await page.getByLabel("E-mail corporativo").fill(invited);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("button", { name: "Aceitar convite" }).click();

  await expect(activeOrganization(page, organization)).toBeVisible();
  await page.goto("/mais");
  await expect(page.getByRole("link", { name: "Membros e convites" })).toHaveCount(0);

  await page.goto("/membros");
  await expect(page.locator("p[role=alert]")).toContainText("Só Owner e Admin");
});

test("quem entra por link mágico retoma o convite na tela inicial", async ({ page, context }) => {
  const organization = `Link ${randomUUID().slice(0, 8)}`;
  await ownerOnMembers(page, organization);
  const invited = uniqueEmail();
  await page.getByLabel("E-mail", { exact: true }).fill(invited);
  await page.getByRole("button", { name: "Enviar convite" }).click();
  await expect(page.getByRole("status")).toContainText("Convite enviado");
  const invitation = await lastInvitationLink(invited);
  await context.clearCookies();

  await page.goto(invitation);
  await page.getByRole("link", { name: "Entrar para aceitar" }).click();
  await page.getByLabel("E-mail corporativo").fill(invited);
  await page.getByRole("button", { name: "Enviar link de acesso" }).click();
  await expect(page.getByRole("status")).toContainText("Enviamos um link");
  await openEmailLink(page, await lastEmailLink(invited));

  await page.getByRole("link", { name: "Ver convite pendente" }).click();
  await page.getByRole("button", { name: "Aceitar convite" }).click();
  await expect(activeOrganization(page, organization)).toBeVisible();
});

test("o único Owner não se rebaixa", async ({ page }) => {
  await ownerOnMembers(page, `Solo ${randomUUID().slice(0, 8)}`);
  await page.getByLabel(/^Papel de /).selectOption("admin");
  await expect(page.locator("p[role=alert]")).toContainText("ao menos um Owner");
});

test("convite revogado some da lista", async ({ page }) => {
  await ownerOnMembers(page, `Revoga ${randomUUID().slice(0, 8)}`);
  const invited = uniqueEmail();
  await page.getByLabel("E-mail", { exact: true }).fill(invited);
  await page.getByRole("button", { name: "Enviar convite" }).click();
  await expect(page.getByText(invited, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Revogar" }).click();
  await expect(page.getByText(invited, { exact: true })).toHaveCount(0);
});
