const LOCALE = "pt-BR";

const numbers = new Intl.NumberFormat(LOCALE);
const percents = new Intl.NumberFormat(LOCALE, { style: "percent", maximumFractionDigits: 1 });

export function formatNumber(value: number): string {
  return numbers.format(value);
}

export function formatPercent(ratio: number): string {
  return percents.format(ratio);
}

// O fuso é o do navegador: no servidor ele é desconhecido, por isso quem chama o informa.
export function formatDateTime(instant: Date, timeZone: string): string {
  return new Intl.DateTimeFormat(LOCALE, {
    dateStyle: "short",
    timeStyle: "short",
    timeZone,
  }).format(instant);
}

// A confiança é uma heurística, não uma probabilidade calibrada: o rótulo nunca sai.
export function confidenceText(value: number): string {
  const clamped = Math.min(Math.max(value, 0), 1);
  return `${percents.format(Math.round(clamped * 100) / 100)} · heurística`;
}
