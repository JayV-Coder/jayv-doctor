import type { ChipTone } from "@/components/ui/chip";

// Tela 21 (#43): estado da conexão com o Jira e o chamado de um Incidente.

type Label = { label: string; tone: ChipTone };

export function jiraState(
  connection: { status: string; project_key: string | null } | null,
): Label {
  if (!connection) return { label: "Não conectado", tone: "neutral" };
  if (connection.status === "needs_reauth") return { label: "Conecte de novo", tone: "danger" };
  if (connection.status !== "active" || !connection.project_key)
    return { label: "Falta o projeto", tone: "warning" };
  return { label: "Conectado", tone: "success" };
}

export function ticketText(ticket: {
  status: string;
  external_key: string | null;
  external_status: string | null;
  error: string | null;
}): string {
  if (ticket.status === "creating") return "Criando o chamado…";
  if (ticket.status === "failed") return `Não abriu: ${ticket.error ?? "erro do Jira"}`;
  return [ticket.external_key, ticket.external_status].filter(Boolean).join(" · ");
}

// Campos customizados com valor fixo, um por linha: `customfield_10010=Sustentação`.
const FIELD = /^(customfield_[0-9]{1,10})\s*=\s*(.+)$/;

export function parseFields(
  value: string,
): { ok: true; fields: Record<string, string> } | { ok: false; message: string } {
  const fields: Record<string, string> = {};
  const lines = value.split("\n");
  for (const [index, raw] of lines.entries()) {
    const line = raw.trim();
    if (!line) continue;
    const [, name, found] = FIELD.exec(line) ?? [];
    if (!name || !found)
      return { ok: false, message: `Linha ${String(index + 1)}: use customfield_<número>=valor.` };
    fields[name] = found.trim();
  }
  return { ok: true, fields };
}

export function fieldsText(fields: Record<string, unknown>): string {
  return Object.entries(fields)
    .map(([name, value]) => `${name}=${String(value)}`)
    .join("\n");
}
