import { AuthShell } from "@/components/auth-shell";
import { SharedDownload } from "./shared-download";

export const metadata = { title: "Relatório compartilhado · Integration AI Doctor" };

// Link compartilhável do Relatório técnico (ADR-0014): abre sem conta. O token vem no fragmento
// da URL, que não chega ao servidor; a página o envia no corpo do pedido.
export default function SharedReportPage() {
  return (
    <AuthShell>
      <section className="stack">
        <h1>Relatório técnico</h1>
        <p>
          Este link foi compartilhado por uma Organização do Integration AI Doctor. Ele vale 7 dias
          e pode ser revogado por quem o criou.
        </p>
        <SharedDownload />
      </section>
    </AuthShell>
  );
}
