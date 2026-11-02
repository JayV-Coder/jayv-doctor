import Link from "next/link";
import { Chip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getMe, listImports, listIntegrations } from "@/lib/api";
import { importSummary, statusLabel, statusTone } from "@/lib/imports/labels";
import { ImportUploader } from "./import-uploader";

export const metadata = { title: "Importar logs · Integration AI Doctor" };

const IMPORTERS = ["owner", "admin", "analyst"];

// Tela 13: Importação manual. O progresso em tempo real chega com o worker de ingestão (#12).
export default async function ImportPage() {
  const [me, integrations, imports] = await Promise.all([
    getMe(),
    listIntegrations(),
    listImports(),
  ]);
  const canImport = IMPORTERS.includes(me?.active_role ?? "");

  return (
    <>
      {canImport && integrations && integrations.length > 0 && (
        <ImportUploader integrations={integrations} />
      )}
      {canImport && integrations?.length === 0 && (
        <EmptyState
          title="Cadastre uma Integração antes"
          action={
            <Link className="btn" href="/integracoes">
              Ir para Integrações
            </Link>
          }
        >
          Cada arquivo importado pertence a uma Integração.
        </EmptyState>
      )}

      <h2 className="label">Importações</h2>
      {imports === null && (
        <ErrorState title="Não foi possível carregar as Importações" action={<ReloadButton />}>
          O serviço não respondeu. Tente de novo em instantes.
        </ErrorState>
      )}
      {imports?.length === 0 && <p className="muted small">Nenhum arquivo importado ainda.</p>}
      {imports?.map((item) => (
        <article key={item.id} className="card" aria-labelledby={`imp-${item.id}`}>
          <div className="row-between">
            <h3 id={`imp-${item.id}`} className="t ell">
              {item.filename}
            </h3>
            <Chip tone={statusTone(item.status)}>{statusLabel(item.status)}</Chip>
          </div>
          {item.error && <p className="small">{item.error}</p>}
          {item.status === "done" && <p className="small">{importSummary(item)}</p>}
        </article>
      ))}
    </>
  );
}
