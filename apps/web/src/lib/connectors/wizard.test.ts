import { describe, expect, it } from "vitest";
import { EMPTY_DRAFT, buildConfig, gcloudCommands, readDraft, validProject } from "./wizard";

describe("validProject", () => {
  it("segue a regra de id de projeto do GCP", () => {
    expect(validProject("acme-integracoes")).toBe(true);
    expect(validProject("Acme")).toBe(false);
    expect(validProject("1acme-x")).toBe(false);
    expect(validProject("acme-")).toBe(false);
  });
});

describe("buildConfig", () => {
  it("monta a config que o conector GCP valida", () => {
    expect(
      buildConfig({
        ...EMPTY_DRAFT,
        project_id: "acme-integracoes",
        services: "sap-order-sync, sf-customer-sync,",
        min_severity: "WARNING",
        filter: '  jsonPayload.app="orders"  ',
        backfill_hours: 168,
      }),
    ).toEqual({
      project_id: "acme-integracoes",
      auth: "key",
      services: ["sap-order-sync", "sf-customer-sync"],
      min_severity: "WARNING",
      filter: 'jsonPayload.app="orders"',
      backfill_hours: 168,
    });
  });

  it("omite o que ficou vazio", () => {
    expect(buildConfig({ ...EMPTY_DRAFT, project_id: "acme-integracoes" })).toEqual({
      project_id: "acme-integracoes",
      auth: "key",
      backfill_hours: 24,
    });
  });
});

describe("readDraft", () => {
  it("recupera o rascunho salvo", () => {
    const saved = { ...EMPTY_DRAFT, step: 3, project_id: "acme-integracoes" };
    expect(readDraft(JSON.stringify(saved))).toEqual(saved);
  });

  it("ignora rascunho corrompido ou de outra versão, e nunca traz credencial", () => {
    expect(readDraft(null)).toEqual(EMPTY_DRAFT);
    expect(readDraft("{")).toEqual(EMPTY_DRAFT);
    expect(readDraft(JSON.stringify({ step: 9 }))).toEqual(EMPTY_DRAFT);
    const withSecret = JSON.stringify({ ...EMPTY_DRAFT, credential: "chave" });
    expect(readDraft(withSecret)).not.toHaveProperty("credential");
  });
});

describe("gcloudCommands", () => {
  it("cria a Service Account, concede só leitura de logs e gera a chave", () => {
    const commands = gcloudCommands("acme-integracoes");
    expect(commands).toHaveLength(3);
    expect(commands[1]).toContain('--role="roles/logging.viewer"');
    expect(commands[1]).toContain("doctor-reader@acme-integracoes.iam.gserviceaccount.com");
    expect(commands[2]).toContain("keys create doctor-reader.json");
  });
});
