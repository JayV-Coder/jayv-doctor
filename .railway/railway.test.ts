// O projeto do Railway (ADR-0024) bate com o código: um serviço por worker que consome tópicos
// (os mesmos do Terraform, em workers/relay/src/aid_relay/emulator.py), os workers chamados pelo
// agendador, a API e o RabbitMQ com volume.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { createRailwayContext, project, type ResourceNode, type ServiceNode } from "railway/iac";
import program from "./railway";

const root = new URL("../", import.meta.url);
const read = (path: string) => readFileSync(new URL(path, root), "utf8");

async function resources(environmentName = "production"): Promise<ResourceNode[]> {
  const definition = await program(createRailwayContext({ environmentName }), project);
  return (definition.resources ?? []).flat();
}

async function services(environmentName = "production"): Promise<Map<string, ServiceNode>> {
  return new Map(
    (await resources(environmentName))
      .filter((resource): resource is ServiceNode => resource.type === "service")
      .map((service) => [service.name, service]),
  );
}

function literal(service: ServiceNode | undefined, name: string): string | null | undefined {
  const value = service?.variables?.[name];
  return value?.type === "literal" ? value.value : undefined;
}

const consumers = [
  ...read("workers/relay/src/aid_relay/emulator.py").matchAll(/"[a-z.]+": \("(\w+)", \d+\)/g),
].map((match) => `worker-${match[1] ?? ""}`);
const scheduled = [
  ...read("workers/runtime/src/aid_worker/scheduler.py").matchAll(/\("[^"]+", "(\w+)", "\//g),
].map((match) => `worker-${match[1] ?? ""}`);

describe("projeto do Railway", () => {
  it("tem um serviço por worker, a API, o agendador e o RabbitMQ", async () => {
    const names = [...(await services()).keys()].sort();
    const expected = [
      ...new Set([...consumers, ...scheduled, "api", "scheduler", "rabbitmq"]),
    ].sort();
    expect(names).toEqual(expected);
  });

  it("os workers consomem o RabbitMQ e atendem na rede privada", async () => {
    const all = await services();
    for (const name of new Set([...consumers, ...scheduled])) {
      const worker = all.get(name);
      expect(worker?.variables?.AMQP_URL).toMatchObject({
        type: "reference",
        resource: "service.rabbitmq",
      });
      expect(literal(worker, "WORKER_NAME")).toBe(name.replace("worker-", ""));
      expect(literal(worker, "PACKAGE")).toBe("aid-worker");
      expect(literal(worker, "PORT")).toBe("8080");
      expect(worker?.deploy?.healthcheckPath).toBe("/healthz");
    }
  });

  it("o agendador chama os workers pelo nome do serviço na rede privada", async () => {
    const scheduler = (await services()).get("scheduler");
    expect(literal(scheduler, "AID_WORKER_URL")).toBe(
      "http://worker-{worker}.railway.internal:8080",
    );
    expect(scheduler?.deploy?.startCommand).toBe("python -m aid_worker.scheduler");
  });

  it("o RabbitMQ guarda as filas num volume, com o nome de nó fixo", async () => {
    const all = await resources();
    const rabbitmq = (await services()).get("rabbitmq");
    expect(rabbitmq?.source?.image).toMatch(/^rabbitmq:\d+\.\d+/);
    expect(literal(rabbitmq, "RABBITMQ_NODENAME")).toBe("rabbit@localhost");
    expect(all.some((resource) => resource.type === "volume")).toBe(true);
  });

  it("o volume fica na região em que foi criado (iad): mudar a região é destrutivo", async () => {
    const volume = (await resources()).find((resource) => resource.type === "volume");
    expect(volume?.type === "volume" ? volume.config?.region : undefined).toBe("iad");
  });

  it("todas as imagens Python saem do mesmo Dockerfile", async () => {
    for (const service of (await services()).values()) {
      if (service.name === "rabbitmq") continue;
      expect(service.build?.builder).toBe("DOCKERFILE");
      expect(service.build?.dockerfilePath).toBe("infrastructure/docker/python.Dockerfile");
      expect(read(service.build?.dockerfilePath ?? "")).toContain(`ARG PACKAGE`);
    }
  });

  it("nenhum segredo fica no código: vêm das variáveis compartilhadas", async () => {
    for (const service of (await services()).values()) {
      for (const [name, value] of Object.entries(service.variables ?? {})) {
        if (/KEY|SECRET|PASS|TOKEN|DB_URL/.test(name) && value.type === "literal") {
          expect(value.value ?? "", name).toMatch(/\$\{\{/);
        }
      }
    }
  });

  it("em qualquer ambiente, o código vem da main", async () => {
    for (const environment of ["production", "development"]) {
      for (const service of (await services(environment)).values()) {
        if (service.name === "rabbitmq") continue;
        expect(service.source?.branch, `${environment}/${service.name}`).toBe("main");
      }
    }
  });

  it("escuta em IPv4: o healthcheck do Railway chega por IPv4", async () => {
    // Com `HOST=::`, o uvicorn (asyncio) liga o socket só em IPv6 e o healthcheck nunca passa.
    for (const service of (await services()).values()) {
      if (service.name === "rabbitmq") continue;
      expect(literal(service, "HOST"), service.name).toBeUndefined();
    }
  });

  it("guarda conexões com o banco: em São Paulo, abrir uma a cada pedido custa segundos", async () => {
    for (const service of (await services()).values()) {
      if (service.name === "rabbitmq") continue;
      expect(literal(service, "DB_POOL_SIZE"), service.name).toBe("5");
    }
  });
});
