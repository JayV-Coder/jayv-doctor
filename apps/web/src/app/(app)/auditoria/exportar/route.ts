import { apiFetch } from "@/lib/api";

// CSV da Trilha de auditoria: o formulário manda os filtros no corpo, e a resposta da API
// (gerada enquanto é enviada) segue direto para o navegador.
export async function POST(request: Request): Promise<Response> {
  const form = await request.formData();
  const value = (name: string) => {
    const found = form.get(name);
    return typeof found === "string" && found.trim() ? found.trim() : undefined;
  };
  const category = value("category");
  const q = value("q");
  const response = await apiFetch("/audit-logs/export", {
    method: "POST",
    body: JSON.stringify({ ...(category && { category }), ...(q && { q }) }),
  }).catch(() => null);
  if (!response?.ok || !response.body) {
    return new Response("Não foi possível exportar agora.", {
      status: response?.status === 403 ? 403 : 502,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }
  return new Response(response.body, {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": 'attachment; filename="auditoria.csv"',
      "cache-control": "no-store",
    },
  });
}
