const CLASSES: Record<string, string> = {
  raw_logs: "Logs brutos",
  events: "Eventos",
  incidents: "Incidentes e Diagnósticos",
  audit: "Auditoria",
};

export function classLabel(dataClass: string): string {
  return CLASSES[dataClass] ?? dataClass;
}

export function daysText(days: number): string {
  return `${String(days)} ${days === 1 ? "dia" : "dias"}`;
}

type Subprocessor = { name: string; purpose: string; region: string };

// Quem trata dados da Organização em nome do Doctor (PRD §8). O provedor de IA depende da
// escolha feita no cadastro da Organização.
export function subprocessors(provider: string): Subprocessor[] {
  const base: Subprocessor[] = [
    {
      name: "Supabase",
      purpose: "Banco de dados, autenticação, armazenamento de arquivos e tempo real",
      region: "Região do projeto Supabase",
    },
    {
      name: "Google Cloud",
      purpose: "API, workers, filas, segredos e logs da plataforma",
      region: "Brasil (southamerica-east1)",
    },
  ];
  if (provider === "vertex") {
    return [
      ...base,
      {
        name: "Google Vertex AI",
        purpose: "Interpretação por IA e embeddings da Base de conhecimento",
        region: "Brasil (southamerica-east1)",
      },
    ];
  }
  return [
    ...base,
    {
      name: "Anthropic",
      purpose: "Interpretação por IA (Claude) das Evidências já sanitizadas",
      region: "Estados Unidos (transferência internacional)",
    },
    {
      name: "Voyage AI",
      purpose: "Embeddings da Base de conhecimento",
      region: "Estados Unidos (transferência internacional)",
    },
  ];
}

const date = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" });

export function deletionText(scheduledFor: string): string {
  return `Exclusão total agendada para ${date.format(new Date(scheduledFor))}`;
}
