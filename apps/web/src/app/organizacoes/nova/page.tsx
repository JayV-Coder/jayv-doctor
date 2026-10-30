"use client";

import Link from "next/link";
import { useActionState, useState } from "react";
import { AuthShell, FormMessage, Win } from "@/components/auth-shell";
import { slugify } from "@/lib/orgs/slug";
import { createOrganization } from "../actions";

const SEGMENTS = ["Consultoria de integração", "Indústria", "Varejo"];

export default function NewOrganizationPage() {
  const [error, action, busy] = useActionState(async (_: string | null, form: FormData) => {
    const failure = await createOrganization(form);
    if (failure === null) window.location.assign("/");
    return failure;
  }, null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);

  return (
    <AuthShell>
      <form className="stack" action={action}>
        <h2 className="title">Crie sua organização</h2>
        <p className="muted small">
          Todos os dados ficam isolados por organização. Você poderá convidar sua equipe depois.
        </p>
        <label className="field">
          Nome da organização
          <input
            name="name"
            required
            minLength={2}
            maxLength={120}
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              if (!slugEdited) setSlug(slugify(event.target.value));
            }}
          />
        </label>
        <label className="field">
          Identificador (URL)
          <input
            name="slug"
            required
            pattern="[a-z0-9][a-z0-9\-]{1,46}[a-z0-9]"
            title="Letras minúsculas, números e hífens"
            autoCapitalize="none"
            value={slug}
            onChange={(event) => {
              setSlug(event.target.value);
              setSlugEdited(true);
            }}
          />
        </label>
        <label className="field">
          Segmento
          <select name="segment" required defaultValue="">
            <option value="" disabled>
              Selecione
            </option>
            {SEGMENTS.map((segment) => (
              <option key={segment}>{segment}</option>
            ))}
          </select>
        </label>
        <Win title="processamento de ia">
          <div className="stack">
            <label className="option">
              <input type="radio" name="llm_provider" value="anthropic" defaultChecked />
              <span>
                <strong>Anthropic Claude</strong>
                <span className="muted small">Padrão · subprocessador fora do Brasil</span>
              </span>
            </label>
            <label className="option">
              <input type="radio" name="llm_provider" value="vertex" />
              <span>
                <strong>Vertex AI (São Paulo)</strong>
                <span className="muted small">Região southamerica-east1</span>
              </span>
            </label>
          </div>
        </Win>
        <label className="option">
          <input type="checkbox" name="dpa_accepted" required />
          <span className="small">Li e aceito o DPA (contrato de tratamento de dados)</span>
        </label>
        <FormMessage error={error} />
        <button className="btn primary" type="submit" disabled={busy}>
          Criar organização
        </button>
        <Link className="btn" href="/">
          Voltar
        </Link>
      </form>
    </AuthShell>
  );
}
