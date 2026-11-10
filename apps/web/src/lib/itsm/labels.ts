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
