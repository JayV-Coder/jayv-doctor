import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

test("Owner cria o canal e a regra do plantão, desliga e define o silêncio", async ({ page }) => {
  test.setTimeout(120_000);
  await ownerWithOrganization(page, `Alertas ${randomUUID().slice(0, 8)}`);
  await page.goto("/mais");
  await page.getByRole("link", { name: "Alertas" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Alertas" })).toBeVisible();
  await expect(page.getByText("Nenhuma regra")).toBeVisible();

  // Canal: webhook fora do Slack é recusado; e-mail para os gestores entra.
  await page.getByRole("button", { name: "Novo canal" }).click();
  const channel = page.getByRole("dialog", { name: "Novo canal" });
  await channel.getByLabel("Tipo").selectOption("slack");
  await channel.getByLabel("Nome").fill("Slack errado");
  await channel.getByLabel("Endereço do webhook").fill("https://evil.test/hook");
  await channel.getByRole("button", { name: "Salvar canal" }).click();
  await expect(channel.getByRole("alert")).toContainText("webhook_url");
  await channel.getByLabel("Tipo").selectOption("email");
  await channel.getByLabel("Nome").fill("E-mail do plantão");
  await channel.getByRole("button", { name: "Salvar canal" }).click();
  await expect(
    page.getByRole("list", { name: "Canais da Organização" }).getByText("E-mail do plantão"),
  ).toBeVisible();

  await page.getByRole("button", { name: "Nova regra" }).click();
  const rule = page.getByRole("dialog", { name: "Nova regra" });
  await rule.getByLabel("Nome").fill("Incidente crítico em produção");
  await rule.getByLabel("Produção").check();
  await rule.getByLabel("E-mail do plantão").check();
  await expectNoHorizontalScroll(page);
  await rule.getByRole("button", { name: "Salvar regra" }).click();

  const card = page.getByRole("article", { name: "Incidente crítico em produção" });
  await expect(card).toContainText("crítico · prd");
  await expect(card).toContainText("E-mail");
  const toggle = card.getByRole("switch");
  await expect(toggle).toBeChecked();
  await toggle.uncheck();
  // Desabilitado enquanto salva: recarregar antes perderia a mudança.
  await expect(toggle).toBeEnabled();
  await page.reload();
  await expect(
    page.getByRole("article", { name: "Incidente crítico em produção" }).getByRole("switch"),
  ).not.toBeChecked();

  // Push e silêncio: o push depende do VAPID do ambiente; o silêncio é de cada Usuário.
  await expect(page.getByRole("list", { name: "Meus canais" })).toContainText(
    "Push neste dispositivo",
  );
  const quiet = page.getByRole("form", { name: "Silêncio fora do plantão" });
  await quiet.getByLabel("Das").fill("22:00");
  await quiet.getByLabel("Até").fill("07:00");
  await quiet.getByRole("button", { name: "Salvar silêncio" }).click();
  await expect(quiet).toContainText("22:00 às 07:00, exceto severidade crítica");
  await expectNoHorizontalScroll(page);
});
