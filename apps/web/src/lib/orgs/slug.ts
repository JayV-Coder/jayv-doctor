const MAX_LENGTH = 48;

function plain(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

export function matchesSearch(name: string, query: string): boolean {
  return plain(name).includes(plain(query.trim()));
}

// Sugestão de identificador; a regra final é a do banco (`tenants.slug`).
export function slugify(name: string): string {
  return plain(name)
    .replace(/[^a-z0-9]+/g, "-")
    .slice(0, MAX_LENGTH)
    .replace(/^-+|-+$/g, "");
}
