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
export function formatDateTime(
  instant: Date,
  timeZone: string,
  { seconds = false }: { seconds?: boolean } = {},
): string {
  return new Intl.DateTimeFormat(LOCALE, {
    dateStyle: "short",
    timeStyle: seconds ? "medium" : "short",
    timeZone,
  }).format(instant);
}

// A confiança é uma heurística, não uma probabilidade calibrada: o rótulo nunca sai. A barra e o
// texto saem do mesmo número, para nunca discordarem.
const decimals = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

// Confiança em decimal (0,68), como no Diagnóstico; o mesmo limite de 0 a 1 da barra.
export function confidenceDecimal(value: number): string {
  return decimals.format(Math.min(Math.max(value, 0), 1));
}

export function confidence(value: number): { percent: number; text: string } {
  const percent = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return { percent, text: `${percents.format(percent / 100)} · heurística` };
}
