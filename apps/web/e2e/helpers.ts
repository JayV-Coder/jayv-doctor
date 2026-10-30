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
      link = /href="([^"]*\/auth\/callback[^"]*)"/.exec(HTML)?.[1]?.replaceAll("&amp;", "&");
      return link !== undefined;
    })
    .toBe(true);
  return link ?? "";
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
