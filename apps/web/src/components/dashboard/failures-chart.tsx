import { bucketLabel, peak } from "@/lib/dashboard/labels";
import { formatNumber } from "@/lib/format";

type Bucket = { start: string; total: number; failed: number };

// Barras de uma série só (falhas por hora ou dia): sem legenda, o título nomeia. Cada barra tem
// o próprio texto no tooltip, e a tabela equivalente fica para leitores de tela.
export function FailuresChart({ buckets, bucket }: { buckets: Bucket[]; bucket: "hour" | "day" }) {
  const top = peak(buckets);
  const max = Math.max(1, ...buckets.map(({ failed }) => failed));
  const unit = bucket === "hour" ? "hora" : "dia";
  const summary = top
    ? `Falhas por ${unit}, pico de ${formatNumber(top.failed)} às ${bucketLabel(top.start, bucket)} UTC`
    : `Nenhuma falha no período`;
  return (
    <section className="card" aria-labelledby="falhas-titulo">
      <div className="row-between">
        <h2 id="falhas-titulo" className="label">
          Falhas por {unit}
        </h2>
        {top && <span className="small">pico {bucketLabel(top.start, bucket)} UTC</span>}
      </div>
      <div className="bars" role="img" aria-label={summary}>
        {buckets.map((item) => (
          <span
            key={item.start}
            className={item === top ? "bar peak" : "bar"}
            style={{ height: `${String(Math.max(2, (item.failed / max) * 100))}%` }}
            title={`${bucketLabel(item.start, bucket)} UTC: ${formatNumber(item.failed)} falhas de ${formatNumber(item.total)}`}
          />
        ))}
      </div>
      <table className="visually-hidden">
        <caption>{summary}</caption>
        <thead>
          <tr>
            <th scope="col">Início (UTC)</th>
            <th scope="col">Falhas</th>
            <th scope="col">Execuções</th>
          </tr>
        </thead>
        <tbody>
          {buckets.map((item) => (
            <tr key={item.start}>
              <td>{bucketLabel(item.start, bucket)}</td>
              <td>{item.failed}</td>
              <td>{item.total}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
