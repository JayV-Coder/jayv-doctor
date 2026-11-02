import { EmptyState } from "@/components/ui/empty-state";

export const metadata = { title: "Incidentes · Integration AI Doctor" };

export default function IncidentsPage() {
  return (
    <EmptyState title="Nenhum Incidente aberto">
      As Regras abrem um Incidente quando uma Execução falha ou foge do esperado.
    </EmptyState>
  );
}
