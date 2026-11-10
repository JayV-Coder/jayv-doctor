// Assistente do Conector Salesforce (ticket #37): a config que vai para a API e a credencial
// que vai para o Vault. A config só escolhe itens da allowlist (fontes, objeto __c e campos);
// nenhum texto de SOQL sai daqui.

export const SOURCES = [
  { id: "integration_log", label: "Objeto de log de integração (__c)" },
  { id: "apex_log", label: "ApexLog" },
  { id: "event_log_file", label: "EventLogFile (Event Monitoring)" },
] as const;

export type SourceId = (typeof SOURCES)[number]["id"];

export type SalesforceDraft = {
  name: string;
  environment: "production" | "sandbox";
  auth: "jwt_bearer" | "web_server";
  object: string;
  message_field: string;
  severity_field: string;
  sources: SourceId[];
  sync_interval_seconds: number;
  integration_id: string;
};

export const EMPTY_SALESFORCE: SalesforceDraft = {
  name: "",
  environment: "production",
  auth: "jwt_bearer",
  object: "",
  message_field: "",
  severity_field: "",
  sources: [],
  sync_interval_seconds: 300,
  integration_id: "",
};

const CUSTOM_OBJECT = /^[A-Za-z][A-Za-z0-9_]{0,39}__c$/;
const FIELD = /^[A-Za-z][A-Za-z0-9_]{0,79}$/;

export function validObject(name: string): boolean {
  return name === "" || CUSTOM_OBJECT.test(name);
}

export function validField(name: string): boolean {
  return name === "" || FIELD.test(name);
}

// Para o teste de conexão: pede todas as fontes, e a resposta diz quais a org tem.
export function probeConfig(draft: SalesforceDraft): Record<string, unknown> {
  return buildSalesforceConfig({
    ...draft,
    sources: draft.object
      ? ["integration_log", "apex_log", "event_log_file"]
      : ["apex_log", "event_log_file"],
  });
}

export function buildSalesforceConfig(draft: SalesforceDraft): Record<string, unknown> {
  const config: Record<string, unknown> = {
    environment: draft.environment,
    auth: draft.auth,
    sources: draft.sources,
  };
  if (draft.sources.includes("integration_log") && draft.object) {
    config.integration_log = {
      object: draft.object,
      timestamp_field: "CreatedDate",
      ...(draft.message_field && { message_field: draft.message_field }),
      ...(draft.severity_field && { severity_field: draft.severity_field }),
    };
  }
  return config;
}

export function buildSalesforceCredential(
  auth: SalesforceDraft["auth"],
  fields: {
    client_id: string;
    username: string;
    private_key: string;
    client_secret: string;
    refresh_token: string;
  },
): string | null {
  const id = fields.client_id.trim();
  if (auth === "jwt_bearer") {
    if (!id || !fields.username.trim() || !fields.private_key.includes("PRIVATE KEY")) return null;
    return JSON.stringify({
      client_id: id,
      username: fields.username.trim(),
      private_key: fields.private_key.trim(),
    });
  }
  if (!id || !fields.client_secret.trim() || !fields.refresh_token.trim()) return null;
  return JSON.stringify({
    client_id: id,
    client_secret: fields.client_secret.trim(),
    refresh_token: fields.refresh_token.trim(),
  });
}
