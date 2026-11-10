// Raias da Timeline por sistema (#40): uma Execução que passa por Salesforce, middleware e SAP
// mostra cada Evento na raia do sistema de onde veio (`source.provider`).

export type Lane = { system: string; label: string; short: string };

// Ordem do fluxo típico: origem, middleware, destino; o resto vem depois, pelo nome.
const KNOWN: Lane[] = [
  { system: "salesforce", label: "Salesforce", short: "SF" },
  { system: "gcp", label: "Google Cloud", short: "GCP" },
  { system: "mulesoft", label: "MuleSoft", short: "Mule" },
  { system: "aws", label: "AWS", short: "AWS" },
  { system: "azure", label: "Azure", short: "Az" },
  { system: "sap", label: "SAP", short: "SAP" },
  { system: "manual", label: "Importação", short: "Imp" },
  { system: "custom", label: "Outros", short: "Out" },
];

export function laneOf(event: { source: Record<string, unknown> }): string {
  const provider = event.source.provider;
  return typeof provider === "string" && provider ? provider : "custom";
}

export function lanes(events: { source: Record<string, unknown> }[]): Lane[] {
  const present = new Set(events.map(laneOf));
  const known = KNOWN.filter((lane) => present.has(lane.system));
  const other = [...present]
    .filter((system) => !KNOWN.some((lane) => lane.system === system))
    .sort()
    .map((system) => ({ system, label: system, short: system.slice(0, 4) }));
  return [...known, ...other];
}

// A chave guardada é `<id do Mapa>:<valor>`; a tela mostra só os valores, sem repetir.
export function crossKeysText(keys: string[]): string {
  const values = keys.map((key) => key.slice(key.indexOf(":") + 1));
  return [...new Set(values)].join(", ");
}
