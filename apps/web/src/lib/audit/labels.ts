type Entry = {
  action: string;
  actor_type: "user" | "system" | "worker";
  actor_label: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
};

export const CATEGORIES = [
  ["", "Todos"],
  ["security", "Segurança"],
  ["diagnosis", "Diagnósticos"],
  ["connectors", "Conectores"],
  ["data", "Dados"],
  ["incidents", "Incidentes"],
] as const;

const ROLES: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  analyst: "Analyst",
  viewer: "Viewer",
};

const ACTIONS: Record<string, string> = {
  "membership.created": "adicionou um membro",
  "membership.deleted": "removeu um membro",
  "membership.updated": "alterou um Vínculo",
  "invitation.created": "convidou alguém",
  "invitation.updated": "alterou um convite",
  "invitation.deleted": "cancelou um convite",
  "integration.created": "criou uma Integração",
  "integration.updated": "alterou uma Integração",
  "integration.deleted": "apagou uma Integração",
  "connector.created": "criou um Conector",
  "connector.updated": "alterou um Conector",
  "connector.deleted": "apagou um Conector",
  "connector.create": "criou um Conector",
  "connector.update": "alterou um Conector",
  "connector.pause": "pausou um Conector",
  "connector.resume": "retomou um Conector",
  "connector.secret.update": "trocou a credencial do Conector",
  "vault.secret_read": "leu a credencial do Conector",
  "org.updated": "alterou a Organização",
  "org.switched": "entrou na Organização",
  "auth.login": "entrou",
  "auth.logout": "saiu",
  "auth.mfa_verified": "confirmou o MFA",
  "auth.mfa_enrolling": "começou a cadastrar o MFA",
  "auth.mfa_enrolled": "cadastrou o MFA",
  "auth.mfa_removed": "removeu o MFA",
  "auth.password_changed": "trocou a senha",
  "auth.recovery_requested": "pediu a recuperação da senha",
  "diagnosis.requested": "pediu um Diagnóstico",
  "diagnosis.reviewed": "revisou um Diagnóstico",
  "diagnosis.auto_changed": "mudou o Diagnóstico automático",
  "incident.update": "alterou um Incidente",
  "raw_log.downloaded": "baixou um Log bruto",
  "knowledge.deleted": "removeu um documento da Base",
  "knowledge.promoted": "promoveu um Incidente à Base",
  "audit.exported": "exportou a trilha de auditoria",
};

// Mudança de acesso e credencial em destaque; revisão humana em verde.
const SERIOUS = ["membership.", "invitation.deleted", "connector.secret", "vault.", "org.updated"];

export function describeEntry(entry: Entry): string {
  if (entry.action === "membership.role_changed") {
    const role = (value: unknown) => (typeof value === "string" ? (ROLES[value] ?? value) : "—");
    const from = role(entry.before?.role);
    const to = role(entry.after?.role);
    return `alterou o papel de um membro: ${from} → ${to}`;
  }
  if (entry.action === "diagnosis.reviewed" && typeof entry.after?.verdict === "string") {
    const verdicts: Record<string, string> = {
      accepted: "aceitou",
      corrected: "corrigiu",
      rejected: "rejeitou",
    };
    const version =
      typeof entry.after.version === "number" ? ` v${String(entry.after.version)}` : "";
    return `${verdicts[entry.after.verdict] ?? "revisou"} o Diagnóstico${version}`;
  }
  return ACTIONS[entry.action] ?? entry.action;
}

export function actorText(entry: Pick<Entry, "actor_type" | "actor_label">): string {
  if (entry.actor_type === "system") return "Sistema";
  if (entry.actor_type === "worker") return "Worker";
  return entry.actor_label ?? "Usuário removido";
}

export function dotTone(action: string): "danger" | "success" | "neutral" {
  if (action === "diagnosis.reviewed" || action === "knowledge.promoted") return "success";
  if (SERIOUS.some((prefix) => action.startsWith(prefix))) return "danger";
  return "neutral";
}
