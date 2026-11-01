export function callbackUrl(siteUrl: string, next?: string): string {
  const url = new URL("/auth/callback", siteUrl);
  // Sem query string na tela inicial: é a URL exata da lista de redirecionamentos do Auth.
  if (next && next !== "/") url.searchParams.set("next", next);
  return url.toString();
}
