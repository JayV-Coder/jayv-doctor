import { AuthShell } from "@/components/auth-shell";

export const metadata = { title: "Continuar · Integration AI Doctor" };

interface Params {
  token_hash?: string;
  type?: string;
  next?: string;
}

export default async function ConfirmPage({ searchParams }: { searchParams: Promise<Params> }) {
  const { token_hash: tokenHash, type, next } = await searchParams;
  return (
    <AuthShell>
      <form className="stack" action="/auth/callback" method="post">
        <input type="hidden" name="token_hash" value={tokenHash ?? ""} />
        <input type="hidden" name="type" value={type ?? ""} />
        <input type="hidden" name="next" value={next ?? ""} />
        <p>Toque em continuar para concluir o acesso.</p>
        <button className="btn primary" type="submit">
          Continuar
        </button>
      </form>
    </AuthShell>
  );
}
