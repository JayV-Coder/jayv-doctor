// Configuração comum dos testes de carga (ticket #33). Tudo vem do ambiente: nada de segredo no
// repositório. `RUN_ID` marca os Eventos da rodada (`attributes.load_run`), para o verify.py
// contar a ponta a ponta.
import { check } from "k6";

export const API_URL = (__ENV.API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
export const RUN_ID = __ENV.RUN_ID || `load-${Date.now()}`;

export function required(name) {
  const value = __ENV[name];
  if (!value) throw new Error(`defina ${name} no ambiente`);
  return value;
}

// UUIDv7 (ms + aleatório): o event_id precisa ser único, senão a deduplicação descarta.
export function uuid7() {
  const hex = Date.now().toString(16).padStart(12, "0");
  const random = () => Math.floor(Math.random() * 16).toString(16);
  let rest = "";
  for (let i = 0; i < 20; i += 1) rest += random();
  const variant = ((parseInt(rest[3], 16) & 0x3) | 0x8).toString(16);
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-7${rest.slice(0, 3)}-${variant}${rest.slice(4, 7)}-${rest.slice(7, 19)}`;
}

// Uma Execução de 4 Eventos (início, chamada, resposta, fim), 1 em 10 com erro 504.
export function execution(integrationId) {
  const executionId = `exec-${uuid7()}`;
  const failed = Math.random() < 0.1;
  const now = Date.now();
  const steps = ["START", "CALL", failed ? "TIMEOUT" : "RESPONSE", "END"];
  return steps.map((step, index) => ({
    schema_version: "1.0",
    event_id: uuid7(),
    integration_id: integrationId,
    execution_id: executionId,
    timestamp: new Date(now + index).toISOString(),
    source: { provider: "sap", service: "PI" },
    operation: `CARGA_${step}`,
    severity: failed && index === 2 ? "ERROR" : "INFO",
    ...(failed && index === 2 ? { error: { http_status: 504, message: "UPSTREAM_TIMEOUT" } } : {}),
    attributes: { load_run: RUN_ID },
  }));
}

export function json(response, name) {
  check(response, { [`${name}: sem 5xx`]: (r) => r.status < 500 });
  return response;
}
