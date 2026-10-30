import Link from "next/link";
import type { ReactNode } from "react";

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <main className="page">
      <div className="brand">
        <span className="logo" aria-hidden="true">
          ❯
        </span>
        <span className="chip">Dados processados no Brasil</span>
        <h1>Integration AI Doctor</h1>
        <p className="muted">
          Diagnóstico <span className="mark">auditável</span> de integrações SAP, Salesforce e
          Google Cloud.
        </p>
      </div>
      {children}
      <p className="foot">
        <Link href="/privacidade">Política de privacidade</Link>
      </p>
    </main>
  );
}

export function Win({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="win">
      <div className="win-head">
        <span>{title}</span>
        <span className="lights" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      </div>
      <div className="win-body">{children}</div>
    </section>
  );
}

export function FormMessage({ error, notice }: { error: string | null; notice?: string | null }) {
  if (error) {
    return (
      <p className="alert" role="alert">
        {error}
      </p>
    );
  }
  if (notice) {
    return (
      <p className="alert notice" role="status">
        {notice}
      </p>
    );
  }
  return null;
}
