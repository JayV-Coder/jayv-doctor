// Conferência no navegador, só para avisar cedo: quem valida a chave de verdade é o Google.
export function serviceAccountEmail(text: string): string | null {
  try {
    const key = JSON.parse(text) as unknown;
    if (typeof key !== "object" || key === null || Array.isArray(key)) return null;
    const { type, client_email, private_key } = key as Record<string, unknown>;
    if (type !== "service_account" || typeof private_key !== "string") return null;
    return typeof client_email === "string" ? client_email : null;
  } catch {
    return null;
  }
}
