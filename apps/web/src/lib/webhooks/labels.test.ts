import { describe, expect, it } from "vitest";
import { deliveryState, eventsText, webhookState } from "./labels";

describe("webhooks na tela", () => {
  it("estado do webhook", () => {
    expect(webhookState({ enabled: true, failure_count: 0, last_status: 200 })).toEqual({
      label: "Ativo",
      tone: "success",
    });
    expect(webhookState({ enabled: true, failure_count: 3, last_status: 503 }).label).toBe(
      "3 falhas seguidas",
    );
    expect(webhookState({ enabled: false, failure_count: 50, last_status: 500 }).label).toBe(
      "Desligado",
    );
  });

  it("eventos", () => {
    expect(eventsText(["incident.opened", "diagnosis.published"])).toBe(
      "Incidente aberto, Diagnóstico publicado",
    );
  });

  it("entrega", () => {
    expect(deliveryState({ status: "succeeded", response_status: 200 }).label).toBe("HTTP 200");
    expect(deliveryState({ status: "pending", response_status: 503 }).label).toBe(
      "Nova tentativa (HTTP 503)",
    );
    expect(deliveryState({ status: "pending", response_status: null }).label).toBe("Na fila");
    expect(deliveryState({ status: "abandoned", response_status: null }).label).toBe("Desistiu");
  });
});
