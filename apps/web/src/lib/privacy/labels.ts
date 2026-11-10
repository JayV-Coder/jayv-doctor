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

// Perfil de IA (#45, ADR-0018): onde as Evidências sanitizadas são processadas.
export const AI_PROFILES: Record<string, { title: string; detail: string }> = {
  standard: {
    title: "Padrão",
    detail: "Claude (Anthropic) e Voyage, nos Estados Unidos",
  },
  br_region: {
    title: "Brasil",
    detail: "Gemini e embeddings no Vertex AI, só em southamerica-east1",
  },
  dedicated: {
    title: "Dedicado",
    detail: "Vertex AI no Brasil com capacidade provisionada só para esta Organização",
  },
};

// O que o DPA diz sobre a IA em cada perfil.
export function dpaText(profile: string): string {
  return profile === "standard"
    ? "Transferência internacional para a Anthropic e a Voyage AI (Estados Unidos), coberta pelas cláusulas-padrão do DPA."
    : "Processamento de IA no Brasil (southamerica-east1), sem transferência internacional para a IA.";
}

const day = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
});

// A verificação diária do perfil: os hosts e a região que a chamada de teste usou. Falha da
// chamada (cota, capacidade) não é divergência de região.
export function checkText(
  check: {
    checked_at: string;
    ok: boolean;
    in_region: boolean;
    region: string | null;
    detail: string | null;
  } | null,
): { text: string; ok: boolean } | null {
  if (!check) return null;
  const when = day.format(new Date(check.checked_at));
  if (check.ok)
    return { text: `Verificado em ${when}: ${check.region ?? "região conferida"}`, ok: true };
  if (!check.in_region)
    return { text: `Divergência de região em ${when}: ${check.detail ?? "conferindo"}`, ok: false };
  return {
    text: `Verificação sem resposta em ${when}, região conferida: ${check.detail ?? ""}`,
    ok: false,
  };
}

// O que muda ao trocar de perfil (mostrado antes de confirmar).
export function profileChangeText(current: string, next: string): string {
  const parts = [
    next === "standard"
      ? "Os próximos Diagnósticos e buscas vão para a Anthropic e a Voyage, nos Estados Unidos (transferência internacional prevista no DPA)."
      : "Os próximos Diagnósticos e buscas ficam no Vertex AI, em southamerica-east1.",
    "A Base de conhecimento é reindexada em segundo plano.",
  ];
  if (current === "dedicated")
    parts.push("Sair do dedicado libera a capacidade: só a operação da plataforma liga de novo.");
  return parts.join(" ");
}

// Reindex depois da troca de perfil: nulo quando a Base já está toda no modelo do perfil.
export function reindexText(reindex: { total: number; current: number }): string | null {
  if (reindex.total === 0 || reindex.current >= reindex.total) return null;
  return `Reindexando a Base: ${String(reindex.current)} de ${String(reindex.total)} documentos no modelo novo. Até terminar, a busca usa o índice anterior quando o perfil permite.`;
}

// Quem trata dados da Organização em nome do Doctor (PRD §8), conforme o perfil de IA.
export function subprocessors(profile: string): Subprocessor[] {
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
  if (profile !== "standard") {
    return [
      ...base,
      {
        name: "Google Vertex AI",
        purpose:
          profile === "dedicated"
            ? "Interpretação por IA em capacidade dedicada e embeddings da Base de conhecimento"
            : "Interpretação por IA e embeddings da Base de conhecimento",
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
