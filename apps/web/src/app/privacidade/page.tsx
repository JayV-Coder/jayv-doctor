import Link from "next/link";
import { AuthShell } from "@/components/auth-shell";

export const metadata = { title: "Privacidade · Integration AI Doctor" };

export default function PrivacyPage() {
  return (
    <AuthShell>
      <section className="stack">
        <h1>Política de privacidade</h1>
        <p>
          Para autenticar você, tratamos seu e-mail, nome e foto de perfil, além de registros de
          acesso. Esses dados servem só para identificar sua conta e proteger o acesso.
        </p>
        <p>Excluir a conta remove o perfil. Dados são processados no Brasil.</p>
        <Link className="btn" href="/">
          Voltar
        </Link>
      </section>
    </AuthShell>
  );
}
