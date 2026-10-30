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

const MFA_PATHS = ["/mfa", "/mfa/cadastro"];

// O desvio para o MFA não pode perder o destino: é assim que a recuperação de senha chega lá.
export function redirectPath(target: string, from: string): string {
  if (!MFA_PATHS.includes(target) || from === "/") return target;
  return `${target}?next=${encodeURIComponent(from)}`;
}

// Só caminhos internos: `next` vem da URL e não pode virar redirecionamento aberto.
// Quem decide é o parser de URL, o mesmo critério do navegador: tab e quebra de linha somem.
export function safeNext(value: string | null): string {
  if (!value?.startsWith("/")) return "/";
  const base = "http://interno.invalid";
  const url = new URL(value, base);
  return url.origin === base ? url.pathname + url.search : "/";
}
