export type TabIcon = "home" | "incidents" | "executions" | "connectors" | "more";

export interface Tab {
  href: string;
  label: string;
  icon: TabIcon;
}

// Barra inferior do mockup (Tela 4). Telas que não são abas abrem a partir de Mais.
export const TABS: readonly Tab[] = [
  { href: "/", label: "Início", icon: "home" },
  { href: "/incidentes", label: "Incidentes", icon: "incidents" },
  { href: "/execucoes", label: "Execuções", icon: "executions" },
  { href: "/conectores", label: "Conectores", icon: "connectors" },
  { href: "/mais", label: "Mais", icon: "more" },
];

const MORE = "/mais";

const TITLES: Record<string, string> = {
  "/membros": "Membros",
};

function within(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function activeTab(pathname: string): string {
  if (pathname === "/") return "/";
  return TABS.find(({ href }) => href !== "/" && within(pathname, href))?.href ?? MORE;
}

export function pageTitle(pathname: string): string {
  const own = Object.entries(TITLES).find(([href]) => within(pathname, href));
  if (own) return own[1];
  const tab = activeTab(pathname);
  return TABS.find(({ href }) => href === tab)?.label ?? "";
}
