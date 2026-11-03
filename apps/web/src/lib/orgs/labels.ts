const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  analyst: "Analyst",
  viewer: "Viewer",
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join("");
}

// Owner e Admin administram a Organização: Membros, Convites e, por isso, MFA obrigatório.
const MANAGER_ROLES = ["owner", "admin"];

export function isManager(role: string | null | undefined): boolean {
  return role != null && MANAGER_ROLES.includes(role);
}

// Ações de escrita na tela: Owner ou Admin com MFA (`aal2`), a mesma regra que a API confere.
// Sem `aal2`, o botão só levaria a um erro no fim.
export function canManage(
  me: { active_role?: string | null; aal?: string | null } | null | undefined,
): boolean {
  return isManager(me?.active_role) && me?.aal === "aal2";
}
