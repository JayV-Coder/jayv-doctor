import Link from "next/link";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { Chip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { apiFetch, getMe } from "@/lib/api";
import { documentDetail, kindLabel } from "@/lib/knowledge/labels";
import { DeleteButton } from "./delete-button";
import { KnowledgeSearch } from "./search";
import { Uploader } from "./uploader";

export const metadata = { title: "Base de conhecimento · Integration AI Doctor" };

const OPERATORS = ["owner", "admin", "analyst"];

type Document = {
  id: string;
  title: string;
  source: string;
  status: string;
  content_type: string | null;
  chunk_count: number;
  error: string | null;
};
type GlobalDocument = { id: string; slug: string; title: string; chunk_count: number };

async function load<T>(path: string): Promise<T | null> {
  const response = await apiFetch(path).catch(() => null);
  return response?.ok ? ((await response.json()) as T) : null;
}

// Tela 14: abas Minha organização e Base global (na URL), busca e envio de documento.
export default async function KnowledgePage({
  searchParams,
}: {
  searchParams: Promise<{ aba?: string | string[] }>;
}) {
  const { aba } = await searchParams;
  const global = aba === "global";
  const [me, documents, globals] = await Promise.all([
    getMe(),
    load<Document[]>("/knowledge/documents"),
    load<GlobalDocument[]>("/knowledge/global"),
  ]);
  const operator = OPERATORS.includes(me?.active_role ?? "");

  return (
    <>
      <div className="row-between">
        <p className="small">Documentos que o Diagnóstico consulta, com a Base global curada.</p>
        {operator && (
          <BottomSheet title="Enviar documento" trigger="Enviar" triggerClassName="btn primary">
            <Uploader />
          </BottomSheet>
        )}
      </div>
      <KnowledgeSearch />
      <div className="row-wrap" aria-label="Abas">
        <Link className="chip-link" aria-pressed={!global} href="/conhecimento">
          Minha organização {documents?.length ?? 0}
        </Link>
        <Link className="chip-link" aria-pressed={global} href="/conhecimento?aba=global">
          Base global {globals?.length ?? 0}
        </Link>
      </div>
      {(global ? globals : documents) === null && (
        <ErrorState title="Não foi possível carregar os documentos" action={<ReloadButton />}>
          O serviço não respondeu. Tente de novo em instantes.
        </ErrorState>
      )}
      {!global && documents?.length === 0 && (
        <p className="muted small">
          Nenhum documento ainda.{" "}
          {operator ? "Envie runbooks, contratos de API e notas de suporte." : ""}
        </p>
      )}
      {!global && documents && documents.length > 0 && (
        <ul className="list" aria-label="Documentos da organização">
          {documents.map((document) => (
            <li key={document.id}>
              <div className="li">
                <Chip tone={document.status === "failed" ? "danger" : "info"}>
                  {kindLabel(document)}
                </Chip>
                <span className="li-text">
                  <span>{document.title}</span>
                  <span className="small">{documentDetail(document)}</span>
                </span>
                {operator && <DeleteButton id={document.id} title={document.title} />}
              </div>
            </li>
          ))}
        </ul>
      )}
      {global && globals && (
        <ul className="list" aria-label="Base global">
          {globals.map((document) => (
            <li key={document.id}>
              <div className="li">
                <Chip tone="neutral">Global</Chip>
                <span className="li-text">
                  <span>{document.title}</span>
                  <span className="small">Curadoria Integration AI Doctor · somente leitura</span>
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="note">
        Documentos da sua organização nunca são usados para diagnosticar incidentes de outras
        organizações.
      </p>
    </>
  );
}
