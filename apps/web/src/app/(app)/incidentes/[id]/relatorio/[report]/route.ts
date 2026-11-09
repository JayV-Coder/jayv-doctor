import { getReport } from "@/lib/reports/api";

// "Baixar" do histórico: a URL assinada (5 min) nasce na hora do clique, com o nome do arquivo.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string; report: string }> },
): Promise<Response> {
  const { report } = await params;
  const found = await getReport(report);
  if (!found?.download_url) {
    return new Response("Relatório indisponível.", {
      status: found ? 409 : 404,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }
  const url = new URL(found.download_url);
  url.searchParams.set("download", `relatorio-${found.id.slice(0, 8)}.${found.format}`);
  return Response.redirect(url, 303);
}
