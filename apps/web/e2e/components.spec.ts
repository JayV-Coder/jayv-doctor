import { expect, test } from "@playwright/test";
import { expectNoHorizontalScroll, signInWithPassword, signUp, uniqueEmail } from "./helpers";

// O catálogo exige sessão como qualquer tela; não precisa de Organização.
test.beforeEach(async ({ page }) => {
  const email = uniqueEmail();
  await signUp(email);
  await signInWithPassword(page, email);
  await expect(page).toHaveURL(/\/organizacoes\/nova/);
});

for (const colorScheme of ["light", "dark"] as const) {
  test(`componentes base no tema ${colorScheme === "light" ? "claro" : "escuro"}`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    await page.goto("/componentes");
    await expect(page.getByRole("heading", { level: 1, name: "Componentes base" })).toBeVisible();
    await expectNoHorizontalScroll(page);
    await expect(page).toHaveScreenshot(`componentes-${colorScheme}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.01,
    });
  });
}

test("a confiança aparece sempre com o rótulo heurística", async ({ page }) => {
  await page.goto("/componentes");
  const bar = page.getByRole("meter", { name: /Confiança/ });
  await expect(bar).toHaveAttribute("aria-valuenow", "82");
  await expect(page.getByText("82% · heurística")).toBeVisible();
});
