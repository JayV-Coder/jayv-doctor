import { describe, expect, it } from "vitest";
import { checkpointText, pauseText } from "./labels";
import {
  EMPTY_SALESFORCE,
  buildSalesforceConfig,
  buildSalesforceCredential,
  probeConfig,
  validObject,
} from "./salesforce";

// Só o cabeçalho do PEM, montado em partes: não é chave nenhuma, e o gitleaks não confunde.
const FAKE_KEY = ["-----BEGIN", "PRIVATE KEY-----", "falsa"].join(" ");

describe("Conector Salesforce", () => {
  it("config só com itens da allowlist", () => {
    const draft = {
      ...EMPTY_SALESFORCE,
      object: "Integration_Log__c",
      message_field: "Message__c",
      sources: ["integration_log" as const, "apex_log" as const],
    };
    expect(buildSalesforceConfig(draft)).toEqual({
      environment: "production",
      auth: "jwt_bearer",
      sources: ["integration_log", "apex_log"],
      integration_log: {
        object: "Integration_Log__c",
        timestamp_field: "CreatedDate",
        message_field: "Message__c",
      },
    });
    expect(probeConfig({ ...EMPTY_SALESFORCE }).sources).toEqual(["apex_log", "event_log_file"]);
    expect(validObject("Account")).toBe(false);
    expect(validObject("Integration_Log__c")).toBe(true);
  });

  it("credencial da Connected App sem senha", () => {
    const fields = {
      client_id: "3MVG9",
      username: "doctor@acme.test",
      private_key: FAKE_KEY,
      client_secret: "",
      refresh_token: "",
    };
    expect(JSON.parse(buildSalesforceCredential("jwt_bearer", fields) ?? "{}")).toEqual({
      client_id: "3MVG9",
      username: "doctor@acme.test",
      private_key: FAKE_KEY,
    });
    expect(buildSalesforceCredential("web_server", fields)).toBeNull();
  });

  it("pausa pelo limite e Checkpoint por fonte", () => {
    expect(pauseText("api_limit")).toContain("80%");
    expect(
      checkpointText({
        sources: {
          apex_log: { at: "2026-11-10T14:01:00+00:00" },
          integration_log: { at: "2026-11-10T14:03:00+00:00" },
        },
      }),
    ).toBe("2026-11-10 14:03:00Z");
  });
});
