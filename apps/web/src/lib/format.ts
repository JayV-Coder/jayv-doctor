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

// A confiança é uma heurística, não uma probabilidade calibrada: o rótulo nunca sai. A barra e o
// texto saem do mesmo número, para nunca discordarem.
export function confidence(value: number): { percent: number; text: string } {
  const percent = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return { percent, text: `${percents.format(percent / 100)} · heurística` };
}
