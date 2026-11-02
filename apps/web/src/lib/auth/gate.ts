export interface SessionState {
  hasSession: boolean;
  role: string | null;
  currentLevel: string | null;
  nextLevel: string | null;
}

const PUBLIC_PATHS = ["/login", "/esqueci-senha"];
// Sem dado de tenant: a tela offline fica no cache do PWA, e o catálogo só mostra componentes.
const OPEN_PATHS = ["/privacidade", "/offline", "/componentes"];
const ENTRY_PATHS = ["/login", "/esqueci-senha", "/mfa", "/mfa/cadastro"];
const ACCEPT_INVITATION_PATH = "/convites/aceitar";
const ADMIN_ROLES = ["owner", "admin"];

// Decide para onde mandar o Usuário antes de abrir `path`; `null` deixa passar.
export function decideRedirect(path: string, state: SessionState): string | null {
  // O aceite decide sozinho o que mostrar: um desvio aqui perderia o token, que vem no fragmento.
  if (path.startsWith("/auth/") || path === ACCEPT_INVITATION_PATH) return null;
  if (OPEN_PATHS.includes(path)) return null;
  if (!state.hasSession) return PUBLIC_PATHS.includes(path) ? null : "/login";

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
