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

// Cores da barra do sistema (meta theme-color) em cada tema; as mesmas do `--bg` em globals.css.
export const THEME_COLORS = { light: "#f4f4f0", dark: "#111210" } as const;

// Aplica a escolha sem recarregar: o atributo que o CSS lê e a cor da barra do sistema.
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
  for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
    const scheme = meta.media.includes("dark") ? "dark" : "light";
    meta.content = THEME_COLORS[theme === "system" ? scheme : theme];
  }
}

// Roda no início do <body>, antes da primeira pintura, e faz o mesmo que `applyTheme` a partir do
// cookie. Assim o layout raiz não lê cookies no servidor e as páginas sem sessão seguem estáticas.
export const THEME_SCRIPT = `(function(){try{var m=document.cookie.match(/(?:^|; )${THEME_COOKIE}=(light|dark)(?:;|$)/);if(!m)return;var t=m[1];document.documentElement.dataset.theme=t;var c={light:"${THEME_COLORS.light}",dark:"${THEME_COLORS.dark}"}[t];document.querySelectorAll('meta[name="theme-color"]').forEach(function(e){e.content=c})}catch(e){}})()`;
