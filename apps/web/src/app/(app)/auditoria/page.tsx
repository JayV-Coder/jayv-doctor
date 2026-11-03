import Link from "next/link";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { searchAudit, type AuditSearch } from "@/lib/audit/api";
import { CATEGORIES } from "@/lib/audit/labels";
import { AuditList } from "./audit-list";

export const metadata = { title: "Auditoria · Integration AI Doctor" };

const VALID = new Set<string>(CATEGORIES.map(([value]) => value).filter(Boolean));

// Tela 18: Owner e Admin com MFA. A categoria fica na URL (chips); o termo de busca, não.
export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{ categoria?: string | string[] }>;
}) {
  const { categoria } = await searchParams;
  const category = typeof categoria === "string" && VALID.has(categoria) ? categoria : null;
  const page = await searchAudit(
    category ? { category: category as NonNullable<AuditSearch["category"]> } : {},
  );

  return (
    <>
      <nav className="row-wrap" aria-label="Categorias">
        {CATEGORIES.map(([value, label]) => (
          <Link
            key={value}
            className="chip-link"
            aria-pressed={(category ?? "") === value}
            href={value ? `/auditoria?categoria=${value}` : "/auditoria"}
          >
            {label}
          </Link>
        ))}
      </nav>
      {page === "forbidden" && (
        <ErrorState title="Auditoria só para Owner e Admin">
          A trilha exige o Papel de Owner ou Admin com MFA ativo nesta sessão.
        </ErrorState>
      )}
      {page === null && (
        <ErrorState title="Não foi possível carregar a auditoria" action={<ReloadButton />}>
          O serviço não respondeu. Tente de novo em instantes.
        </ErrorState>
      )}
      {page !== null && page !== "forbidden" && (
        <AuditList key={category ?? "todos"} category={category} initial={page} />
      )}
      <p className="note">Registros imutáveis · retidos por 365 dias.</p>
    </>
  );
}
