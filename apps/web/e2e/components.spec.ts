import { expect, test } from "@playwright/test";
import { expectNoHorizontalScroll } from "./helpers";

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
