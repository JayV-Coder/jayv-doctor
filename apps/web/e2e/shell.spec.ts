import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { activeOrganization, expectNoHorizontalScroll, ownerWithOrganization } from "./helpers";

const TABS = [
  ["Início", /\/$/],
  ["Incidentes", /\/incidentes$/],
  ["Execuções", /\/execucoes$/],
  ["Conectores", /\/conectores$/],
  ["Mais", /\/mais$/],
] as const;

test("navega pelas 5 abas sem rolagem horizontal e com a aba ativa destacada", async ({
  page,
}, testInfo) => {
  const organization = `Shell ${randomUUID().slice(0, 8)}`;
  await ownerWithOrganization(page, organization);
  await page.goto("/");
  await expect(activeOrganization(page, organization)).toBeVisible();

  const nav = page.getByRole("navigation", { name: "Navegação principal" });
  for (const [label, url] of TABS) {
    await nav.getByRole("link", { name: label }).click();
    await expect(page).toHaveURL(url);
    await expect(page.getByRole("heading", { level: 1, name: label })).toBeVisible();
    await expect(nav.getByRole("link", { name: label })).toHaveAttribute("aria-current", "page");
    await expect(nav.locator("[aria-current=page]")).toHaveCount(1);
    await expectNoHorizontalScroll(page);
  }

  // Celular: barra no rodapé. Desktop: barra lateral à esquerda.
  const box = await nav.boundingBox();
  const viewport = page.viewportSize();
  if (!box || !viewport) throw new Error("navegação sem área visível");
  if (testInfo.project.name === "desktop") {
    expect(box.x).toBe(0);
    expect(box.height).toBeGreaterThan(viewport.height / 2);
  } else {
    expect(box.y + box.height).toBeCloseTo(viewport.height, 0);
    expect(box.width).toBe(viewport.width);
  }
});

test("Membros abre a partir de Mais, com a aba Mais ativa", async ({ page }) => {
  const organization = `Mais ${randomUUID().slice(0, 8)}`;
  await ownerWithOrganization(page, organization);
  await page.goto("/mais");
  await page.getByRole("link", { name: "Membros e convites" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Membros" })).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Navegação principal" });
  await expect(nav.getByRole("link", { name: "Mais" })).toHaveAttribute("aria-current", "page");
});

test("o tema escolhido vale na hora e depois de recarregar", async ({ page }) => {
  await ownerWithOrganization(page, `Tema ${randomUUID().slice(0, 8)}`);
  await page.goto("/mais");
  const html = page.locator("html");

  await page.getByRole("radio", { name: "Escuro" }).check();
  await expect(html).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("radio", { name: "Escuro" })).toBeChecked();

  await page.getByRole("radio", { name: "Sistema" }).check();
  await expect(html).not.toHaveAttribute("data-theme");
  await page.reload();
  await expect(html).not.toHaveAttribute("data-theme");
});

test("depois de sair, o PWA offline não mostra dados da Organização", async ({ page, context }) => {
  const organization = `Offline ${randomUUID().slice(0, 8)}`;
  const email = await ownerWithOrganization(page, organization);
  await page.goto("/");
  await expect(activeOrganization(page, organization)).toBeVisible();
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });

  await page.goto("/mais");
  await page.getByRole("button", { name: "Sair" }).click();
  await expect(page).toHaveURL(/\/login/);

  await context.setOffline(true);
  for (const path of ["/", "/incidentes", "/mais"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: "Sem conexão" })).toBeVisible();
    await expect(page.getByText(organization)).toHaveCount(0);
    await expect(page.getByText(email)).toHaveCount(0);
  }
  await context.setOffline(false);
});

test("o manifesto torna o PWA instalável", async ({ request }) => {
  const response = await request.get("/manifest.webmanifest");
  expect(response.ok()).toBe(true);
  const manifest = (await response.json()) as {
    name: string;
    start_url: string;
    display: string;
    lang: string;
    icons: { sizes: string; purpose?: string; src: string }[];
  };
  expect(manifest).toMatchObject({
    name: "Integration AI Doctor",
    start_url: "/",
    display: "standalone",
    lang: "pt-BR",
  });
  const sizes = manifest.icons.map(({ sizes }) => sizes);
  expect(sizes).toEqual(expect.arrayContaining(["192x192", "512x512"]));
  expect(manifest.icons.some(({ purpose }) => purpose === "maskable")).toBe(true);
  for (const icon of manifest.icons) {
    expect((await request.get(icon.src)).headers()["content-type"]).toBe("image/png");
  }
});
