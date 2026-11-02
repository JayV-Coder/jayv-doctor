const KEY = "convite-pendente";

// Fica no navegador, não na aba: o link mágico pode abrir em outra, e o login nem sempre volta ao
// aceite. Sai no aceite. Sem storage, basta abrir de novo o link do e-mail.
export function savePendingInvitation(token: string): void {
  try {
    window.localStorage.setItem(KEY, token);
  } catch {
    return;
  }
}

export function pendingInvitation(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function forgetPendingInvitation(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    return;
  }
}
