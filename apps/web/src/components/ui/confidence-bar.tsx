import { confidence, confidenceDecimal } from "@/lib/format";

// Confiança é heurística, nunca probabilidade: o rótulo vai junto da barra, sempre. O Diagnóstico
// mostra o valor em decimal (0,68) com o rótulo longo, como no mockup da Tela 6.
export function ConfidenceBar({
  value,
  label = "Confiança",
  decimal = false,
}: {
  value: number;
  label?: string;
  decimal?: boolean;
}) {
  const { percent, text } = confidence(value);
  const shown = decimal ? confidenceDecimal(value) : text;
  return (
    <div
      className="confidence"
      role="meter"
      aria-label="Confiança do Diagnóstico"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      aria-valuetext={text}
    >
      <div className="row-between">
        <span className="label">{label}</span>
        <span className="small">{shown}</span>
      </div>
      <div className="confidence-track" aria-hidden="true">
        <i style={{ width: `${String(percent)}%` }} />
      </div>
    </div>
  );
}
