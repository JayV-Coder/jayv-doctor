// GCP falso para o E2E do assistente de Conector (ticket #16): troca o JWT da Service Account por
// um token e responde ao `entries:list` com 48 entradas. O projeto `acme-sem-permissao` recebe o
// 403 que o Cloud Logging manda quando falta roles/logging.viewer. A API aponta para cá pelas
// variáveis AID_GCP_OAUTH_URL e AID_GCP_LOGGING_URL, só no E2E.
import { createServer } from "node:http";
import process from "node:process";

const PORT = Number(process.env.FAKE_GCP_PORT ?? 8095);

function send(response, status, body) {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

function salesforce(request, response) {
  const limit = { "sforce-limit-info": "api-usage=1500/15000" };
  if (request.url === "/sf/services/oauth2/token") {
    return send(response, 200, {
      access_token: "sessao-falsa",
      instance_url: `http://127.0.0.1:${String(PORT)}/sf`,
    });
  }
  if (request.url?.endsWith("/sobjects")) {
    response.writeHead(200, { "content-type": "application/json", ...limit });
    return response.end(
      JSON.stringify({ sobjects: [{ name: "Integration_Log__c" }, { name: "ApexLog" }] }),
    );
  }
  if (request.url?.includes("/query?")) {
    response.writeHead(200, { "content-type": "application/json", ...limit });
    return response.end(JSON.stringify({ records: [] }));
  }
  send(response, 404, [{ errorCode: "NOT_FOUND" }]);
}

createServer((request, response) => {
  let raw = "";
  request.on("data", (chunk) => (raw += chunk));
  request.on("end", () => {
    // Salesforce falso (#37), em /sf: org sem Event Monitoring, com 10% do limite diário usado.
    if (request.url?.startsWith("/sf/")) return salesforce(request, response);
    if (request.method === "GET") return send(response, 200, { ok: true });
    if (request.url === "/token") {
      return send(response, 200, { access_token: "token-falso", expires_in: 3600 });
    }
    if (request.url === "/v2/entries:list") {
      const body = JSON.parse(raw || "{}");
      if (body.resourceNames?.[0] === "projects/acme-sem-permissao") {
        return send(response, 403, {
          error: {
            code: 403,
            status: "PERMISSION_DENIED",
            message: "Permission 'logging.logEntries.list' denied",
          },
        });
      }
      const now = Date.now();
      const entries = Array.from({ length: 48 }, (_, index) => ({
        insertId: `e2e-${index}`,
        timestamp: new Date(now - (48 - index) * 60_000).toISOString(),
        severity: "ERROR",
        resource: { type: "cloud_run_revision", labels: { service_name: "orders-sync" } },
        jsonPayload: { message: "Timeout ao chamar o SAP" },
      }));
      return send(response, 200, { entries });
    }
    send(response, 404, { error: { code: 404 } });
  });
}).listen(PORT, "127.0.0.1");
