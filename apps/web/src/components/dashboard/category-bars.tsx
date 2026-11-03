import { categoryLabel } from "@/lib/dashboard/labels";
import { formatNumber } from "@/lib/format";

// Barras horizontais com o rótulo e o número em texto ao lado: a barra só reforça a ordem.
export function CategoryBars({ items }: { items: { category: string; count: number }[] }) {
  const max = Math.max(1, ...items.map(({ count }) => count));
  return (
    <section className="card" aria-labelledby="categorias-titulo">
      <h2 id="categorias-titulo" className="label">
        Falhas por categoria
      </h2>
      {items.length === 0 && <p className="muted small">Nenhuma falha no período.</p>}
      <ul className="hbars" aria-label="Falhas por categoria">
        {items.map((item) => (
          <li key={item.category} className="hbar">
            <span className="ell">{categoryLabel(item.category)}</span>
            <span className="track" aria-hidden="true">
              <i style={{ width: `${String((item.count / max) * 100)}%` }} />
            </span>
            <span>{formatNumber(item.count)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
