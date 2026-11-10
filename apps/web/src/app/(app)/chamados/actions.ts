"use server";

import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { send as post, type Outcome } from "@/lib/forms/send";

export type { Outcome };

const OPTIONS = {
  page: "/chamados",
  messages: {
    jira_not_configured: "Conecte e configure o Jira antes.",
    invalid_site: "O site escolhido não está na autorização.",
    jira_unavailable: "O app do Jira não está configurado na plataforma.",
    not_found: "Jira não conectado.",
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
  return post(
    "/itsm/jira",
    {
      method: "PUT",
      body: JSON.stringify({
        cloud_id: text(form, "site"),
        project_key: text(form, "project").toUpperCase(),
        issue_type: text(form, "issue-type"),
        sync_status: form.get("sync") === "on",
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

export async function disconnectJira(key: string): Promise<Outcome> {
  return post("/itsm/jira", { method: "DELETE" }, key, OPTIONS);
}

export async function openTicket(incident: string, key: string): Promise<Outcome> {
  return post(`/incidents/${encodeURIComponent(incident)}/tickets`, { method: "POST" }, key, {
    ...OPTIONS,
    page: `/incidentes/${incident}`,
  });
}
