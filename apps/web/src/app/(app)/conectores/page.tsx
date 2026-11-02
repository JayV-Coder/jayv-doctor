import Link from "next/link";
import { EmptyState } from "@/components/ui/empty-state";

export const metadata = { title: "Conectores · Integration AI Doctor" };

export default function ConnectorsPage() {
  return (
    <EmptyState
      title="Nenhum Conector configurado"
      action={
        <Link className="btn" href="/importar">
          Importar logs
        </Link>
      }
    >
      Os Conectores coletam logs do Google Cloud, do Salesforce e do SAP para a sua Organização.
      Enquanto isso, você pode importar um arquivo exportado.
    </EmptyState>
  );
}
