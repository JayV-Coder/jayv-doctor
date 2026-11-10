"use server";

import { redirect } from "next/navigation";
import { apiFetch, type ServiceNowSaved } from "@/lib/api";
import { send as post, type Outcome } from "@/lib/forms/send";
import { parseFields } from "@/lib/itsm/labels";

export type { Outcome };

const OPTIONS = {
  page: "/chamados",
  messages: {
    itsm_not_configured: "Conecte e configure o ITSM em Chamados (ITSM) antes.",
    invalid_site: "O site escolhido não está na autorização.",
    jira_unavailable: "O app do Jira não está configurado na plataforma.",
    not_found: "Conexão não encontrada.",
    secret_required: "Informe o client secret (primeira vez ou instância nova).",
  },
};

// O consentimento é no Atlassian: a API devolve a URL com o `state` de uso único.
export async function connectJira(): Promise<string | null> {
  const response = await apiFetch("/itsm/jira/authorize", { method: "POST" }).catch(() => null);
  if (!response?.ok) {
    const found = (await response?.json().catch(() => null)) as { code?: string } | null;
    const messages: Record<string, string> = OPTIONS.messages;
    return messages[found?.code ?? ""] ?? "Não foi possível começar agora.";
  }
  const { url } = (await response.json()) as { url: string };
  redirect(url);
}

function text(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
}

export async function configureJira(form: FormData, key: string): Promise<Outcome> {
  const custom = parseFields(text(form, "fields"));
  if (!custom.ok) return { ok: false, message: custom.message, offline: false };
  return post(
    "/itsm/jira",
    {
      method: "PUT",
      body: JSON.stringify({
        cloud_id: text(form, "site"),
        project_key: text(form, "project").toUpperCase(),
        issue_type: text(form, "issue-type"),
        sync_status: form.get("sync") === "on",
        // Sempre enviados: salvar a tela não apaga os campos que já estavam.
        custom_fields: custom.fields,
        priority_map: {
          critical: text(form, "priority-critical") || "Highest",
          high: text(form, "priority-high") || "High",
          medium: text(form, "priority-medium") || "Medium",
          low: text(form, "priority-low") || "Low",
        },
      }),
    },
    key,
    OPTIONS,
  );
}

const SYSTEMS = ["sap", "salesforce", "gcp", "other"] as const;

export async function configureServiceNow(
  form: FormData,
  key: string,
): Promise<Outcome<ServiceNowSaved>> {
  const groups = Object.fromEntries(
    SYSTEMS.map((system) => [system, text(form, `group-${system}`)]).filter(([, group]) => group),
  ) as Record<string, string>;
  return post<ServiceNowSaved>(
    "/itsm/servicenow",
    {
      method: "PUT",
      body: JSON.stringify({
        instance_url: text(form, "instance").toLowerCase().replace(/\/+$/, ""),
        client_id: text(form, "client-id"),
        // Em branco mantém o secret que já está no Vault.
        client_secret: text(form, "client-secret") || null,
        assignment_groups: groups,
        default_group: text(form, "default-group") || null,
        sync_status: form.get("sync") === "on",
        rotate_hook: form.get("rotate") === "on",
      }),
    },
    key,
    OPTIONS,
  );
}

export async function disconnectServiceNow(key: string): Promise<Outcome> {
  return post("/itsm/servicenow", { method: "DELETE" }, key, OPTIONS);
}

export async function disconnectJira(key: string): Promise<Outcome> {
  return post("/itsm/jira", { method: "DELETE" }, key, OPTIONS);
}

export async function openTicket(
  incident: string,
  provider: "jira" | "servicenow",
  key: string,
): Promise<Outcome> {
  const path = `/incidents/${encodeURIComponent(incident)}/tickets?provider=${provider}`;
  return post(path, { method: "POST" }, key, {
    ...OPTIONS,
    page: `/incidentes/${incident}`,
  });
}
