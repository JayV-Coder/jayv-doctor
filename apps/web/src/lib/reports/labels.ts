import { formatDateTime } from "../format";
import { incidentCode } from "../incidents/labels";

const FORMATS: Record<string, string> = { pdf: "PDF", md: "Markdown" };
const ZONE = "America/Sao_Paulo";

export function formatLabel(format: string): string {
  return FORMATS[format] ?? format;
}

export function previewName(number: number, format: string): string {
  return `${incidentCode(number).toLowerCase()}.${format} · pré-visualização`;
}

export function downloadLabel(format: string): string {
  return `Baixar ${formatLabel(format)}`;
}

// Histórico da Tela 19: formato, versão do Diagnóstico, quando e, se não pronto, o estado.
export function reportLine(report: {
  format: string;
  status: string;
  diagnosis_version: number | null;
  created_at: string;
}): string {
  const parts = [
    formatLabel(report.format),
    report.diagnosis_version === null
      ? "sem Diagnóstico"
      : `Diagnóstico v${String(report.diagnosis_version)}`,
    formatDateTime(new Date(report.created_at), ZONE),
  ];
  if (report.status === "queued" || report.status === "running") parts.push("gerando…");
  if (report.status === "failed") parts.push("falhou");
  return parts.join(" · ");
}

export function shareExpiry(expiresAt: string): string {
  return `vale até ${formatDateTime(new Date(expiresAt), ZONE)}`;
}
