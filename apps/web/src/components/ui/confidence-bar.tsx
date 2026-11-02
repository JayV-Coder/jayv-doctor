import { confidenceText } from "@/lib/format";

// Confiança é heurística, nunca probabilidade: o rótulo vai junto da barra, sempre.
export function ConfidenceBar({ value }: { value: number }) {
  const percent = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  const text = confidenceText(value);
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
        <span className="label">Confiança</span>
        <span className="small">{text}</span>
      </div>
      <div className="confidence-track" aria-hidden="true">
        <i style={{ width: `${String(percent)}%` }} />
      </div>
    </div>
  );
}
