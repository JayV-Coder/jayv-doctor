import { notFound } from "next/navigation";
import { connection } from "next/server";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { KpiTile } from "@/components/ui/kpi-tile";
import { ListItem } from "@/components/ui/list-item";
import { Skeleton } from "@/components/ui/skeleton";
import { formatNumber, formatPercent } from "@/lib/format";

export const metadata = { title: "Componentes base · Integration AI Doctor", robots: "noindex" };

// Catálogo para os snapshots visuais do E2E. Fora dos testes, a rota não existe. `connection()`:
// a variável é lida a cada requisição, não congelada no build.
export default async function ComponentsPage() {
  await connection();
  if (process.env.COMPONENT_CATALOG !== "1") notFound();

  return (
    <main className="content">
      <h1>Componentes base</h1>

      <Card title="Chip">
        <div className="row-wrap">
          <Chip tone="danger">Crítico</Chip>
          <Chip tone="warning">Alto</Chip>
          <Chip>Médio</Chip>
          <Chip tone="info">v1 · revisar</Chip>
          <Chip tone="success">Aceito</Chip>
        </div>
      </Card>

      <div className="kpis">
        <KpiTile label="Execuções" value={formatNumber(18402)} detail="+6% vs. ontem" />
        <KpiTile label="Taxa de erro" value={formatPercent(0.034)} detail="+1,1 p.p." />
      </div>

      <ul className="list">
        <ListItem href="/componentes" title="Membros e convites" />
        <ListItem title="Provedor de IA" detail="Anthropic Claude" />
      </ul>

      <Card title="Diagnóstico">
        <ConfidenceBar value={0.82} />
      </Card>

      <EmptyState title="Nenhum Incidente aberto">
        As Regras abrem um Incidente quando uma Execução falha.
      </EmptyState>

      <ErrorState title="Não foi possível carregar">O serviço não respondeu.</ErrorState>

      <Skeleton />

      <BottomSheet title="Filtros" trigger="Abrir filtros">
        <p className="muted small">Conteúdo do painel.</p>
      </BottomSheet>
    </main>
  );
}
