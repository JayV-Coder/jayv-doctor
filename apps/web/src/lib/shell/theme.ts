export type Theme = "light" | "dark" | "system";

export const THEME_COOKIE = "tema";
const ONE_YEAR = 60 * 60 * 24 * 365;

export function parseTheme(value: string | undefined): Theme {
  return value === "light" || value === "dark" ? value : "system";
}

// No cookie, e não no localStorage: o servidor já entrega o HTML no tema certo, sem piscar.
export function themeCookie(theme: Theme): string {
  const [value, maxAge] = theme === "system" ? ["", "0"] : [theme, String(ONE_YEAR)];
  return `${THEME_COOKIE}=${value}; Path=/; Max-Age=${maxAge}; SameSite=Lax`;
}
