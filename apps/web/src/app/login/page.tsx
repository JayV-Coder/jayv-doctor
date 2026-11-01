import { AuthShell } from "@/components/auth-shell";
import { safeNext } from "@/lib/auth/gate";
import { LoginForm } from "./login-form";

export const metadata = { title: "Entrar · Integration AI Doctor" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ erro?: string; next?: string }>;
}) {
  const { erro, next } = await searchParams;
  const error = erro === "link" ? "Link inválido ou expirado. Peça um novo." : null;
  return (
    <AuthShell>
      <LoginForm initialError={error} next={safeNext(next ?? null)} />
    </AuthShell>
  );
}
