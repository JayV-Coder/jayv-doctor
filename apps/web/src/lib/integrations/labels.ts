import type { ChipTone } from "@/components/ui/chip";
import { formatPercent } from "../format";

export type Environment = "dev" | "hml" | "prd";
export type System = "sap" | "salesforce" | "gcp" | "other";

export const ENVIRONMENTS: { value: Environment; label: string }[] = [
  { value: "prd", label: "Produção" },
  { value: "hml", label: "Homologação" },
  { value: "dev", label: "Desenvolvimento" },
];

export const SYSTEMS: { value: System; label: string }[] = [
  { value: "sap", label: "SAP" },
  { value: "salesforce", label: "Salesforce" },
  { value: "gcp", label: "Google Cloud" },
  { value: "other", label: "Outro" },
];

const TONES: Record<Environment, ChipTone> = { prd: "danger", hml: "info", dev: "neutral" };

export function environmentLabel(environment: Environment): string {
  return ENVIRONMENTS.find(({ value }) => value === environment)?.label ?? environment;
}

export function environmentTone(environment: Environment): ChipTone {
  return TONES[environment];
}

export function flowLabel(source: System, target: System): string {
  const label = (system: System) => SYSTEMS.find(({ value }) => value === system)?.label;
  return `${label(source) ?? source} → ${label(target) ?? target}`;
}

// Sem Execução não há taxa: mostrar 0% passaria a ideia de que está tudo bem.
export function errorRateText(rate: number | null | undefined): string {
  return rate == null ? "sem Execuções" : formatPercent(rate);
}
