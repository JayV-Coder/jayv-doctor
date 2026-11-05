const RESOURCES: Record<string, string> = {
  events_ingested: "Eventos no mês",
  diagnoses_llm: "Diagnósticos com IA",
  storage_bytes: "Armazenamento",
  connectors_active: "Conectores ativos",
  members: "Membros (com convites)",
};

export function resourceLabel(resource: string): string {
  return RESOURCES[resource] ?? resource;
}

const compact = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

export function amountText(resource: string, value: number): string {
  if (resource === "storage_bytes") return `${compact.format(value / 1e9)} GB`;
  if (value >= 1e6) return `${compact.format(value / 1e6)} mi`;
  if (value >= 1e3 && resource === "events_ingested") return `${compact.format(value / 1e3)} mil`;
  return compact.format(value);
}

// Aviso da Tela 17: aos 80% e quando a Cota acaba, com o efeito no produto.
export function quotaWarning(resource: string, ratio: number, tolerance = 1.1): string | null {
  if (ratio >= 1) {
    if (resource === "diagnoses_llm") {
      return "Cota de IA esgotada: novos Diagnósticos rodam só com as Regras";
    }
    if (resource === "events_ingested") {
      return `Cota esgotada: a ingestão é recusada acima de ${String(Math.round(tolerance * 100))}%`;
    }
    if (resource === "storage_bytes") return "Armazenamento no limite do plano";
    return "Limite do plano atingido: novos itens são bloqueados";
  }
  if (ratio >= 0.8) {
    const percent = Math.round(ratio * 100);
    return resource === "diagnoses_llm"
      ? `${String(percent)}% — depois disso, só Regras`
      : `${String(percent)}% da Cota`;
  }
  return null;
}
