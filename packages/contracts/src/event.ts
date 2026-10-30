import { Ajv2020 } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import type { EventV1 } from "./generated/event.v1";
import eventSchemaV1 from "../schemas/event.v1.json" with { type: "json" };

export type { EventBusinessContext, EventError, EventSource, EventV1 } from "./generated/event.v1";
export { eventSchemaV1 };

export const TENANT_ID_REJECTED =
  "tenant_id não é aceito no payload: o tenant vem da identidade autenticada do Conector";

export type EventValidationResult = { ok: true; event: EventV1 } | { ok: false; errors: string[] };

const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
const validate = ajv.compile<EventV1>(eventSchemaV1);

/** Valida um payload contra o Contrato de evento v1 (mesmo schema usado pelo Python). */
export function validateEvent(payload: unknown): EventValidationResult {
  const errors = hasTenantId(payload) ? [TENANT_ID_REJECTED] : [];
  if (validate(payload) && errors.length === 0) return { ok: true, event: payload };
  for (const error of validate.errors ?? []) {
    errors.push(`${error.instancePath || "$"}: ${error.message ?? "inválido"}`);
  }
  return { ok: false, errors };
}

function hasTenantId(payload: unknown): boolean {
  return typeof payload === "object" && payload !== null && "tenant_id" in payload;
}
