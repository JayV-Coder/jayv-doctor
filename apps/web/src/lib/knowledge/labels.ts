import { formatNumber } from "../format";

const TYPES: Record<string, { label: string; type: string }> = {
  pdf: { label: "PDF", type: "application/pdf" },
  md: { label: "MD", type: "text/markdown" },
  markdown: { label: "MD", type: "text/markdown" },
  txt: { label: "TXT", type: "text/plain" },
  docx: {
    label: "DOCX",
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  },
};

export const ACCEPT = ".pdf,.md,.markdown,.txt,.docx";
export const MAX_BYTES = 20 * 1024 * 1024;

export function contentTypeOf(filename: string): string | null {
  const extension = filename.split(".").pop()?.toLowerCase() ?? "";
  return TYPES[extension]?.type ?? null;
}

export function kindLabel(document: { source: string; content_type: string | null }): string {
  if (document.source === "incident") return "INC";
  return Object.values(TYPES).find(({ type }) => type === document.content_type)?.label ?? "DOC";
}

export function documentDetail(document: {
  status: string;
  chunk_count: number;
  error: string | null;
}): string {
  switch (document.status) {
    case "ready":
      return `${formatNumber(document.chunk_count)} ${document.chunk_count === 1 ? "Fragmento" : "Fragmentos"} · indexado`;
    case "failed":
      return `Falhou: ${document.error ?? "erro desconhecido."}`;
    case "pending":
      return "Aguardando o envio";
    default:
      return "Indexando…";
  }
}
