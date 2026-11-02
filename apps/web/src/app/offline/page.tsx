import { AuthShell } from "@/components/auth-shell";

export const metadata = { title: "Sem conexão · Integration AI Doctor" };

// Fica no cache do service worker: não pode trazer nada de sessão nem de Organização.
export default function OfflinePage() {
  return (
    <AuthShell>
      <section className="stack">
        <h2 className="title">Sem conexão</h2>
        <p className="muted">
          Conecte-se para ver os dados da sua organização. Nada dela fica guardado neste aparelho.
        </p>
        <a className="btn primary" href="/">
          Tentar de novo
        </a>
      </section>
    </AuthShell>
  );
}
