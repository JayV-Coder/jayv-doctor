import { AuthShell } from "@/components/auth-shell";
import { LoginForm } from "./login-form";

export const metadata = { title: "Entrar · Integration AI Doctor" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ erro?: string }>;
}) {
  const { erro } = await searchParams;
  const error = erro === "link" ? "Link inválido ou expirado. Peça um novo." : null;
  return (
    <AuthShell>
      <LoginForm initialError={error} />
    </AuthShell>
  );
}
