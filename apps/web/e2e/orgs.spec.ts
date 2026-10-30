import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import {
  expectNoHorizontalScroll,
  fillOtp,
  signInWithPassword,
  signUp,
  totp,
  uniqueEmail,
} from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

async function fillOrganization(page: Page, name: string): Promise<void> {
  await page.getByLabel("Nome da organização").fill(name);
  await page.getByLabel("Segmento").selectOption("Varejo");
  await page.getByLabel("Li e aceito o DPA").check();
  await page.getByRole("button", { name: "Criar organização" }).click();
}

// Owner sem fator é levado ao cadastro assim que o JWT traz o Papel.
async function enrollFactor(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/mfa\/cadastro/);
  await page.getByRole("button", { name: "Gerar QR code" }).click();
  const secret = await page.locator("code.secret").innerText();
  await fillOtp(page, totp(secret));
  await page.getByRole("button", { name: "Confirmar" }).click();
  await expect(page).toHaveURL(/\/seguranca/);
  await page.goto("/");
}

test("cria Organizações, troca entre elas e a tela muda junto", async ({ page }) => {
  const email = uniqueEmail();
  const suffix = randomUUID().slice(0, 8);
  await signUp(email);
  await signInWithPassword(page, email);

  await page.getByRole("link", { name: "Criar organização" }).click();
  await expectNoHorizontalScroll(page);
  await fillOrganization(page, `Acme ${suffix}`);
  await enrollFactor(page);
  await expect(page.getByRole("heading", { name: `Acme ${suffix}` })).toBeVisible();

  await page.getByRole("button", { name: `Acme ${suffix}` }).click();
  await expectNoHorizontalScroll(page);
  await page.getByRole("link", { name: "Criar nova organização" }).click();
  await fillOrganization(page, `Varejo ${suffix}`);
  await expect(page.getByRole("heading", { name: `Varejo ${suffix}` })).toBeVisible();

  await page.getByRole("button", { name: `Varejo ${suffix}` }).click();
  await page.getByLabel("Buscar organização").fill("acme");
  await expect(
    page.getByRole("button", { name: new RegExp(`Varejo ${suffix}.*Owner`) }),
  ).toBeHidden();
  await page.getByRole("button", { name: new RegExp(`Acme ${suffix}.*Owner`) }).click();

  await expect(page.getByRole("heading", { name: `Acme ${suffix}` })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: `Acme ${suffix}` })).toBeVisible();
});

test("identificador repetido mostra erro em pt-BR", async ({ page }) => {
  const name = `Duplicada ${randomUUID().slice(0, 8)}`;
  const first = uniqueEmail();
  await signUp(first);
  await signInWithPassword(page, first);
  await page.getByRole("link", { name: "Criar organização" }).click();
  await fillOrganization(page, name);
  await expect(page).toHaveURL(/\/mfa\/cadastro/);
  await page.context().clearCookies();

  const second = uniqueEmail();
  await signUp(second);
  await signInWithPassword(page, second);
  await page.getByRole("link", { name: "Criar organização" }).click();
  await page.getByLabel("Vertex AI").check();
  await fillOrganization(page, name);
  await expect(page.locator("p[role=alert]")).toContainText("identificador já está em uso");
  await expect(page.getByLabel("Vertex AI")).toBeChecked();
  await expect(page.getByLabel("Segmento")).toHaveValue("Varejo");
});

test("a API recusa trocar para Organização sem Vínculo", async ({ page, request }) => {
  const email = uniqueEmail();
  await signUp(email);
  await signInWithPassword(page, email);
  await expect(page.getByText(`Sessão ativa: ${email}`)).toBeVisible();

  const cookies = await page.context().cookies();
  const raw = cookies.find((cookie) => cookie.name.endsWith("-auth-token"))?.value ?? "";
  const session = JSON.parse(Buffer.from(raw.replace(/^base64-/, ""), "base64url").toString()) as {
    access_token: string;
  };
  const response = await request.post(`http://127.0.0.1:8000/api/v1/orgs/${randomUUID()}/switch`, {
    headers: { authorization: `Bearer ${session.access_token}` },
  });
  expect(response.status()).toBe(403);
  expect(((await response.json()) as { code: string }).code).toBe("not_a_member");
});
