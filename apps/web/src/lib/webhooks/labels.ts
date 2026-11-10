import type { ChipTone } from "@/components/ui/chip";

// Webhooks de saída (#42): estado do webhook, eventos e cada entrega no histórico.

type Label = { label: string; tone: ChipTone };

export const EVENTS: { value: string; label: string }[] = [
  { value: "incident.opened", label: "Incidente aberto" },
  { value: "incident.updated", label: "Incidente atualizado" },
  { value: "incident.resolved", label: "Incidente resolvido" },
  { value: "diagnosis.published", label: "Diagnóstico publicado" },
  { value: "diagnosis.reviewed", label: "Diagnóstico revisado" },
];

export function eventsText(events: string[]): string {
  return events
    .map((event) => EVENTS.find((item) => item.value === event)?.label ?? event)
    .join(", ");
}

export function webhookState(hook: {
  enabled: boolean;
  failure_count: number;
  last_status: number | null;
}): Label {
  if (!hook.enabled) return { label: "Desligado", tone: "danger" };
  if (hook.failure_count > 0)
    return { label: `${String(hook.failure_count)} falhas seguidas`, tone: "warning" };
  return { label: "Ativo", tone: "success" };
}

export function deliveryState(delivery: { status: string; response_status: number | null }): Label {
  const http = delivery.response_status ? `HTTP ${String(delivery.response_status)}` : null;
  switch (delivery.status) {
    case "succeeded":
      return { label: http ?? "Entregue", tone: "success" };
    case "abandoned":
      return { label: "Desistiu", tone: "danger" };
    case "pending":
      return http
        ? { label: `Nova tentativa (${http})`, tone: "warning" }
        : { label: "Na fila", tone: "info" };
    default:
      return { label: http ?? "Falhou", tone: "danger" };
  }
}
