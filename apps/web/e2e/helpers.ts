import { createHmac, randomUUID } from "node:crypto";
import { expect, type Page } from "@playwright/test";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://127.0.0.1:54321";
const SUPABASE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";
const MAILPIT_URL = process.env.MAILPIT_URL ?? "http://127.0.0.1:54324";

// Aleatória a cada execução; o prefixo atende à política de senha do Auth.
export function randomPassword(): string {
  return `Aa1-${randomUUID()}`;
}

export const PASSWORD = randomPassword();

export function uniqueEmail(): string {
  return `e2e-${randomUUID()}@acme.test`;
}

export async function signUp(email: string): Promise<void> {
  const response = await fetch(`${SUPABASE_URL}/auth/v1/signup`, {
    method: "POST",
    headers: { apikey: SUPABASE_KEY, "content-type": "application/json" },
    body: JSON.stringify({ email, password: PASSWORD }),
  });
  expect(response.status).toBe(200);
}

// Link do último e-mail da caixa; o Mailpit é o Inbucket da stack atual do Supabase.
export async function lastEmailLink(email: string): Promise<string> {
  let link: string | undefined;
  await expect
    .poll(async () => {
      const search = await fetch(
        `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`,
      );
      const { messages } = (await search.json()) as { messages: { ID: string }[] };
      const id = messages[0]?.ID;
      if (!id) return false;
      const message = await fetch(`${MAILPIT_URL}/api/v1/message/${id}`);
      const { HTML } = (await message.json()) as { HTML: string };
      link = /href="([^"]*\/auth\/confirmar[^"]*)"/.exec(HTML)?.[1]?.replaceAll("&amp;", "&");
      return link !== undefined;
    })
    .toBe(true);
  return link ?? "";
}

// Link do convite: o token vem no fragmento, que aparece só no texto do e-mail.
export async function lastInvitationLink(email: string): Promise<string> {
  let link: string | undefined;
  await expect
    .poll(async () => {
      const search = await fetch(
        `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`,
      );
      const { messages } = (await search.json()) as { messages: { ID: string }[] };
      const id = messages[0]?.ID;
      if (!id) return false;
      const message = await fetch(`${MAILPIT_URL}/api/v1/message/${id}`);
      const { Text } = (await message.json()) as { Text: string };
      link = /(http\S+\/convites\/aceitar#\S+)/.exec(Text)?.[1];
      return link !== undefined;
    })
    .toBe(true);
  return link ?? "";
}

// A verificação só acontece no clique: um scanner de e-mail que abre o link não gasta o token.
export async function openEmailLink(page: Page, link: string): Promise<void> {
  await page.goto(link);
  await page.getByRole("button", { name: "Continuar" }).click();
}

export function totp(secret: string, now = Date.now()): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bits = Array.from(secret.replace(/=+$/, ""))
    .map((char) => alphabet.indexOf(char).toString(2).padStart(5, "0"))
    .join("");
  const key = Buffer.from((bits.match(/.{8}/g) ?? []).map((byte) => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(now / 30_000)));
  const hmac = createHmac("sha1", key).update(counter).digest();
  const offset = (hmac[19] ?? 0) & 0xf;
  return String((hmac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

export async function fillOtp(page: Page, code: string): Promise<void> {
  await page.getByLabel("Dígito 1").fill(code);
}

export async function signInWithPassword(
  page: Page,
  email: string,
  password = PASSWORD,
): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("E-mail corporativo").fill(email);
  await page.getByRole("button", { name: "Entrar com senha" }).click();
  await page.getByLabel("Senha").fill(password);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
}

export async function expectNoHorizontalScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
}

// Sem Organização, o portão leva direto ao cadastro dela.
export async function fillOrganization(page: Page, name: string): Promise<void> {
  await expect(page).toHaveURL(/\/organizacoes\/nova/);
  await page.getByLabel("Nome da organização").fill(name);
  await page.getByLabel("Segmento").selectOption("Varejo");
  await page.getByLabel("Li e aceito o DPA").check();
  await page.getByRole("button", { name: "Criar organização" }).click();
}

// Owner sem fator é levado ao cadastro assim que o JWT traz o Papel.
export async function enrollFactor(page: Page): Promise<string> {
  await expect(page).toHaveURL(/\/mfa\/cadastro/);
  await page.getByRole("button", { name: "Gerar QR code" }).click();
  const secret = await page.locator("code.secret").innerText();
  await fillOtp(page, totp(secret));
  await page.getByRole("button", { name: "Confirmar" }).click();
  await expect(page).toHaveURL(/\/seguranca/);
  return secret;
}

export async function ownerWithOrganization(page: Page, name: string): Promise<string> {
  const email = uniqueEmail();
  await signUp(email);
  await signInWithPassword(page, email);
  await fillOrganization(page, name);
  await enrollFactor(page);
  return email;
}

// O seletor fica no topo do shell, com o nome da Organização ativa.
export function activeOrganization(page: Page, name: string) {
  return page.getByRole("button", { name: `Trocar de organização: ${name}` });
}

// Na tela de Integrações, pela folha "Nova integração".
export async function createIntegration(page: Page, name: string): Promise<void> {
  await page.getByRole("button", { name: "Nova", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "Nova integração" });
  await sheet.getByLabel("Nome").fill(name);
  await sheet.getByLabel("Origem").selectOption("Salesforce");
  await sheet.getByLabel("Destino").selectOption("SAP");
  await sheet.getByLabel("Ambiente").selectOption("Produção");
  await sheet.getByRole("button", { name: "Salvar integração" }).click();
}
