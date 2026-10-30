export function callbackUrl(siteUrl: string, next?: string): string {
  const url = new URL("/auth/callback", siteUrl);
  if (next) url.searchParams.set("next", next);
  return url.toString();
}
