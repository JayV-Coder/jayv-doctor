import { EmptyState } from "@/components/ui/empty-state";

export const metadata = { title: "Execuções · Integration AI Doctor" };

export default function ExecutionsPage() {
  return (
    <EmptyState title="Nenhuma Execução recebida">
      Cada Execução reúne os Eventos de uma transação de ponta a ponta, vindos dos Conectores ou de
      uma Importação manual.
    </EmptyState>
  );
}
