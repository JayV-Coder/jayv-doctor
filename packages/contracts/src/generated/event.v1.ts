/* Gerado a partir de schemas/event.v1.json. Não edite: rode `make contracts`. */

/**
 * Contrato de evento v1: formato canônico de todo Evento normalizado, independente da fonte. O tenant nunca vem no payload; é atribuído pela identidade autenticada do Conector ou do token de ingestão.
 */
export interface EventV1 {
  /**
   * Versão do contrato. Major 1; o minor cresce em mudanças compatíveis.
   */
  schema_version: string;
  /**
   * UUIDv7 do Evento (ordenável pelo tempo).
   */
  event_id: string;
  /**
   * Identificador da Integração a que o Evento pertence.
   */
  integration_id: string;
  /**
   * Identificador técnico da Execução, quando a fonte o fornece.
   */
  execution_id?: string;
  /**
   * Identificador de trace distribuído, quando houver.
   */
  trace_id?: string;
  /**
   * Instante do Evento em RFC 3339, com fuso e no máximo microssegundos.
   */
  timestamp: string;
  source: EventSource;
  /**
   * Operação de negócio ou técnica (ex.: create_order).
   */
  operation: string;
  severity: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  error?: EventError;
  business_context?: EventBusinessContext;
  /**
   * Atributos planos (sem objetos aninhados). Os limites mantêm o bloco abaixo de 16 KB.
   */
  attributes?: {
    [k: string]: string | number | boolean | null;
  };
}
export interface EventSource {
  provider: "gcp" | "salesforce" | "sap" | "aws" | "azure" | "mulesoft" | "manual" | "custom";
  service: string;
  resource?: string;
}
export interface EventError {
  category:
    | "TIMEOUT"
    | "AUTH"
    | "RATE_LIMIT"
    | "VALIDATION"
    | "BUSINESS_REJECTION"
    | "DUPLICATE"
    | "CONNECTIVITY"
    | "UNKNOWN";
  http_status?: number;
  code?: string;
  message?: string;
}
export interface EventBusinessContext {
  entity_type?: string;
  /**
   * Referência de negócio. Após a Sanitização é sempre persistida como hmac:<hex>.
   */
  entity_reference?: string;
}
