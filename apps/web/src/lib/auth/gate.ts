export interface SessionState {
  hasSession: boolean;
  role: string | null;
  currentLevel: string | null;
  nextLevel: string | null;
}

const PUBLIC_PATHS = ["/login", "/esqueci-senha", "/privacidade"];
const ENTRY_PATHS = ["/login", "/esqueci-senha", "/mfa", "/mfa/cadastro"];
const ADMIN_ROLES = ["owner", "admin"];

// Decide para onde mandar o Usuário antes de abrir `path`; `null` deixa passar.
export function decideRedirect(path: string, state: SessionState): string | null {
  if (path.startsWith("/auth/")) return null;
  const isPublic = PUBLIC_PATHS.includes(path);
  if (!state.hasSession) return isPublic ? null : "/login";
  if (path === "/privacidade") return null;

  if (state.currentLevel !== "aal2" && state.nextLevel === "aal2") {
    return path === "/mfa" ? null : "/mfa";
  }
  const mustEnroll =
    state.role !== null && ADMIN_ROLES.includes(state.role) && state.nextLevel !== "aal2";
  if (mustEnroll) return path === "/mfa/cadastro" ? null : "/mfa/cadastro";

  return ENTRY_PATHS.includes(path) ? "/" : null;
}

// Só caminhos internos: `next` vem da URL e não pode virar redirecionamento aberto.
export function safeNext(value: string | null): string {
  if (!value?.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return "/";
  return value;
}
