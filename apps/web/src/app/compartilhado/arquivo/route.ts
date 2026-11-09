const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

// Sem sessão: repassa o token (no corpo) à API, que confere o link e devolve o arquivo.
export async function POST(request: Request): Promise<Response> {
  const { token } = (await request.json().catch(() => ({}))) as { token?: unknown };
  if (typeof token !== "string" || token.length < 32 || token.length > 128) {
    return new Response("Link inválido.", { status: 404 });
  }
  const response = await fetch(`${API_URL}/api/v1/shared-reports`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token }),
    cache: "no-store",
  }).catch(() => null);
  if (!response?.ok || !response.body) {
    return new Response("Não foi possível abrir o link.", {
      status: response?.status === 404 ? 404 : 502,
    });
  }
  return new Response(response.body, {
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/octet-stream",
      "content-disposition": response.headers.get("content-disposition") ?? "attachment",
      "cache-control": "no-store",
    },
  });
}
