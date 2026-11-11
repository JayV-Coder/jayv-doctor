import { expect, test } from "@playwright/test";
import {
  expectNoHorizontalScroll,
  fillOtp,
  lastEmailLink,
  openEmailLink,
  randomPassword,
  signInWithPassword,
  signUp,
  totp,
  uniqueEmail,
} from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

test("visitante sem sessão vai para o login", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
});

test("login completo em 390 px com o teclado virtual aberto", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 420 });
  await page.goto("/login");
  await page.getByLabel("E-mail corporativo").focus();
  await expectNoHorizontalScroll(page);
  await expect(page.getByRole("link", { name: "Política de privacidade" })).toBeAttached();
  const box = await page.getByRole("button", { name: "Enviar link de acesso" }).boundingBox();
  expect(box?.height).toBeGreaterThanOrEqual(44);
});

test("entra pelo link enviado por e-mail, que só vale uma vez", async ({ page }) => {
  const email = uniqueEmail();
  await page.goto("/login");
  await page.getByLabel("E-mail corporativo").fill(email);
  await page.getByRole("button", { name: "Enviar link de acesso" }).click();
  await expect(page.getByRole("status")).toContainText("Enviamos um link");

  const link = await lastEmailLink(email);
  await page.goto(link);
  await page.reload();
  await page.getByRole("button", { name: "Continuar" }).click();
  await expect(page.getByText(`Sessão ativa: ${email}`)).toBeVisible();

  await page.getByRole("button", { name: "Sair" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await openEmailLink(page, link);
  await expect(page.locator("p[role=alert]")).toContainText("Link inválido ou expirado");
});

test("senha errada mostra erro em pt-BR e a certa entra", async ({ page }) => {
  const email = uniqueEmail();
  await signUp(email);
  await signInWithPassword(page, email, "senha-errada-000");
  await expect(page.locator("p[role=alert]")).toHaveText("E-mail ou senha incorretos.");
  await signInWithPassword(page, email);
  await expect(page.getByText(`Sessão ativa: ${email}`)).toBeVisible();
});

test("redefine a senha pelo link do e-mail", async ({ page }) => {
  const email = uniqueEmail();
  const newPassword = randomPassword();
  await signUp(email);
  await page.goto("/esqueci-senha");
  await page.getByLabel("E-mail corporativo").fill(email);
  await page.getByRole("button", { name: "Enviar link de redefinição" }).click();
  await expect(page.getByRole("status")).toContainText("Se houver uma conta");

  await openEmailLink(page, await lastEmailLink(email));
  await expect(page).toHaveURL(/\/redefinir-senha$/);
  await page.getByLabel("Nova senha").fill(newPassword);
  await page.getByRole("button", { name: "Salvar nova senha" }).click();
  await expect(page.getByText(`Sessão ativa: ${email}`)).toBeVisible();

  await page.getByRole("button", { name: "Sair" }).click();
  // Sair cancela o push antes de enviar (#41): espera chegar ao login.
  await expect(page).toHaveURL(/\/login$/);
  await signInWithPassword(page, email, newPassword);
  await expect(page.getByText(`Sessão ativa: ${email}`)).toBeVisible();
});

test("cadastra MFA e passa a exigir o código no login", async ({ page }) => {
  const email = uniqueEmail();
  await signUp(email);
  await signInWithPassword(page, email);
  await page.getByRole("link", { name: "Segurança da conta" }).click();
  await page.getByRole("button", { name: "Gerar QR code" }).click();
  const secret = await page.locator("code.secret").innerText();
  await fillOtp(page, totp(secret));
  await page.getByRole("button", { name: "Confirmar" }).click();
  await expect(page.getByRole("status")).toContainText("App autenticador cadastrado");
  await page.goto("/");
  await page.getByRole("button", { name: "Sair" }).click();
  // Sair cancela o push antes de enviar (#41): espera chegar ao login.
  await expect(page).toHaveURL(/\/login$/);

  await signInWithPassword(page, email);
  await expect(page).toHaveURL(/\/mfa$/);
  await page.goto("/");
  await expect(page).toHaveURL(/\/mfa$/);

  await fillOtp(page, "000000");
  await page.getByRole("button", { name: "Verificar" }).click();
  await expect(page.locator("p[role=alert]")).toHaveText("Código incorreto ou expirado.");

  await fillOtp(page, totp(secret));
  await page.getByRole("button", { name: "Verificar" }).click();
  await expect(page.getByText(`Sessão ativa: ${email}`)).toBeVisible();
  await expectNoHorizontalScroll(page);
});

test("quem tem MFA redefine a senha depois de verificar o código", async ({ page }) => {
  const email = uniqueEmail();
  const newPassword = randomPassword();
  await signUp(email);
  await signInWithPassword(page, email);
  await page.getByRole("link", { name: "Segurança da conta" }).click();
  await page.getByRole("button", { name: "Gerar QR code" }).click();
  const secret = await page.locator("code.secret").innerText();
  await fillOtp(page, totp(secret));
  await page.getByRole("button", { name: "Confirmar" }).click();
  await expect(page.getByRole("status")).toContainText("App autenticador cadastrado");
  await page.goto("/");
  await page.getByRole("button", { name: "Sair" }).click();
  // Sair cancela o push antes de enviar (#41): espera chegar ao login.
  await expect(page).toHaveURL(/\/login$/);

  await page.goto("/esqueci-senha");
  await page.getByLabel("E-mail corporativo").fill(email);
  await page.getByRole("button", { name: "Enviar link de redefinição" }).click();
  await expect(page.getByRole("status")).toContainText("Se houver uma conta");

  await openEmailLink(page, await lastEmailLink(email));
  await expect(page).toHaveURL(/\/mfa\?next=%2Fredefinir-senha$/);
  await fillOtp(page, totp(secret));
  await page.getByRole("button", { name: "Verificar" }).click();
  await expect(page).toHaveURL(/\/redefinir-senha$/);
  await page.getByLabel("Nova senha").fill(newPassword);
  await page.getByRole("button", { name: "Salvar nova senha" }).click();
  await expect(page.getByText(`Sessão ativa: ${email}`)).toBeVisible();
});

test("o callback recusa POST de outra origem", async ({ page }) => {
  const response = await page.request.post("/auth/callback", {
    headers: { origin: "https://mal.test" },
    form: { token_hash: "qualquer", type: "magiclink" },
    maxRedirects: 0,
  });
  expect(response.status()).toBe(303);
  expect(response.headers().location).toContain("/login?erro=link");
});

test("token expirado é renovado de forma transparente", async ({ page, context }) => {
  const email = uniqueEmail();
  await signUp(email);
  await signInWithPassword(page, email);
  await expect(page.getByText(`Sessão ativa: ${email}`)).toBeVisible();

  const cookies = await context.cookies();
  const session = cookies.find((cookie) => cookie.name.endsWith("-auth-token"));
  if (!session) throw new Error("cookie de sessão ausente");
  const decoded = JSON.parse(
    Buffer.from(session.value.replace("base64-", ""), "base64url").toString(),
  ) as { access_token: string; expires_at: number };
  const expired = Buffer.from(JSON.stringify({ ...decoded, expires_at: 1 })).toString("base64url");
  await context.addCookies([{ ...session, value: `base64-${expired}` }]);

  await page.reload();
  await expect(page.getByText(`Sessão ativa: ${email}`)).toBeVisible();
  const renewed = (await context.cookies()).find((cookie) => cookie.name === session.name);
  expect(renewed?.value).not.toBe(`base64-${expired}`);
});

test("cria a conta pelo login com as regras da senha e entra", async ({ page }) => {
  const email = uniqueEmail();
  const password = randomPassword();
  await page.goto("/login");
  await page.getByRole("button", { name: "Ainda não tem conta? Criar conta" }).click();
  await page.getByLabel("E-mail corporativo").fill(email);
  await page.getByLabel("Nome").fill("Ana Integradora");
  await page.getByLabel("Senha", { exact: true }).fill("curta");
  const create = page.getByRole("button", { name: "Criar conta" });
  await expect(create).toBeDisabled();
  await expect(page.getByRole("list", { name: "Regras da senha" })).toContainText(
    "Ao menos 12 caracteres (pendente)",
  );
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByLabel("Confirmar senha").fill(`${password}x`);
  await expect(page.getByText("As senhas não conferem.")).toBeVisible();
  await page.getByLabel("Confirmar senha").fill(password);
  await expectNoHorizontalScroll(page);
  await create.click();
  // A stack local não pede confirmação de e-mail: a conta já entra (no projeto hospedado, a
  // tela pede para confirmar pelo e-mail antes).
  await expect(page).not.toHaveURL(/\/login/);
  await page.context().clearCookies();
  await signInWithPassword(page, email, password);
  await expect(page).not.toHaveURL(/\/login/);
});
