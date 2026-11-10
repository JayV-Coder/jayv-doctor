import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

test("retenção, envio ao LLM, subprocessadores, titular e exclusão total", async ({ page }) => {
  test.setTimeout(120_000);
  await ownerWithOrganization(page, `Privacidade ${randomUUID().slice(0, 8)}`);
  await page.goto("/mais");

  const retention = page.getByRole("list", { name: "Retenção" });
  await expect(retention).toContainText("Logs brutos");
  await expect(retention).toContainText("30 dias");
  await expectNoHorizontalScroll(page);
  await page.getByRole("button", { name: "Alterar a retenção de Logs brutos" }).click();
  const sheet = page.getByRole("dialog", { name: "Retenção de Logs brutos" });
  await sheet.getByLabel(/Dias/).fill("15");
  await sheet.getByRole("button", { name: "Salvar" }).click();
  await expect(retention).toContainText("15 dias");

  const llm = page.getByRole("switch", { name: /Enviar evidências ao LLM/ });
  await expect(llm).toBeChecked();
  // A mudança é otimista: espera a Server Action responder antes de recarregar.
  const saved = page.waitForResponse((response) => response.request().method() === "POST");
  await llm.uncheck();
  await saved;
  await page.reload();
  await expect(page.getByRole("switch", { name: /Enviar evidências ao LLM/ })).not.toBeChecked();

  await page.getByRole("link", { name: "Subprocessadores" }).click();
  const list = page.getByRole("list", { name: "Subprocessadores" });
  await expect(list).toContainText("Anthropic");
  await expect(list).toContainText("Estados Unidos");
  await expect(page.getByText("O envio de evidências ao LLM está desligado")).toBeVisible();

  // Perfil de IA (#45): o Owner com MFA passa para o Brasil; subprocessadores e DPA mudam junto.
  await page.goto("/mais");
  const profile = page.getByRole("group", { name: "Perfil de IA" });
  await expect(profile.getByRole("radio", { name: /Padrão/ })).toBeChecked();
  await expect(profile.getByRole("radio", { name: /Dedicado/ })).toHaveCount(0);
  const changed = page.waitForResponse((response) => response.request().method() === "POST");
  await profile.getByRole("radio", { name: /Brasil/ }).check();
  await changed;
  await expectNoHorizontalScroll(page);
  await page.reload();
  await expect(
    page.getByRole("group", { name: "Perfil de IA" }).getByRole("radio", { name: /Brasil/ }),
  ).toBeChecked();
  await page.getByRole("link", { name: "Subprocessadores" }).click();
  await expect(list).toContainText("Google Vertex AI");
  await expect(list).not.toContainText("Anthropic");
  await expect(page.getByRole("note")).toContainText("sem transferência internacional");

  await page.goto("/titular");
  await page.getByLabel("Referência de negócio do titular").fill("4500012345");
  await page.getByRole("button", { name: "Localizar" }).click();
  await expect(page.getByText("Nenhum Evento com essa Referência.")).toBeVisible();
  expect(page.url()).not.toContain("4500012345");

  await page.goto("/mais");
  await page.getByRole("button", { name: "Solicitar exclusão total" }).click();
  const confirm = page.getByRole("dialog", { name: "Excluir a Organização" });
  const slug = await confirm.locator("p b").innerText();
  const submit = confirm.getByRole("button", { name: "Excluir em 7 dias" });
  await expect(submit).toBeDisabled();
  await confirm.getByLabel("Identificador da Organização").fill(slug);
  await submit.click();
  await expect(page.getByText(/Exclusão total agendada para/)).toBeVisible();
  await page.getByRole("button", { name: "Cancelar a exclusão" }).click();
  await expect(page.getByText(/Exclusão total agendada para/)).toHaveCount(0);
});
