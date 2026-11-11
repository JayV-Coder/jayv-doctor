import Link from "next/link";
import { safeNext } from "@/lib/auth/gate";
import { LoginForm } from "./login-form";

export const metadata = { title: "Entrar · Integration AI Doctor" };

// Login no desenho do jayv-coder: uma coluna estreita e centrada, marca, título e subtítulo,
// formulário, provedores e a troca entre entrar e criar conta.
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ erro?: string; next?: string }>;
}) {
  const { erro, next } = await searchParams;
  const error = erro === "link" ? "Link inválido ou expirado. Peça um novo." : null;
  return (
    <main className="auth">
      <div className="auth-column">
        <header className="auth-head">
          <span className="auth-mark" aria-hidden="true">
            ❯
          </span>
          <h1>Entrar no Integration AI Doctor</h1>
          <p>Diagnóstico auditável de integrações SAP, Salesforce e Google Cloud.</p>
        </header>
        <LoginForm initialError={error} next={safeNext(next ?? null)} />
        <p className="auth-foot">
          <Link href="/privacidade">Política de privacidade</Link>
        </p>
      </div>
    </main>
  );
}
