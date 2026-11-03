"use client";

import { useState, type ChangeEvent } from "react";
import { FormMessage } from "@/components/auth-shell";
import { ACCEPT, MAX_BYTES, contentTypeOf } from "@/lib/knowledge/labels";
import { createDocument, finishDocument } from "./actions";

// O arquivo vai direto do navegador para o Storage, pela URL assinada: não passa pela API.
function put(url: string, file: File, type: string): Promise<boolean> {
  return fetch(url, { method: "PUT", headers: { "content-type": type }, body: file })
    .then((response) => response.ok)
    .catch(() => false);
}

export function Uploader() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function send(file: File): Promise<string | null> {
    const type = contentTypeOf(file.name);
    if (!type) return "Use PDF, Markdown, TXT ou DOCX.";
    if (file.size > MAX_BYTES) return "O arquivo passa de 20 MB.";
    const created = await createDocument({
      title: file.name.replace(/\.[^.]+$/, ""),
      filename: file.name,
      content_type: type,
      size_bytes: file.size,
    });
    if ("error" in created) return created.error;
    if (!(await put(created.upload_url, file, type))) return "O envio do arquivo falhou.";
    return finishDocument(created.id);
  }

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    void send(file)
      .catch(() => "Não foi possível enviar o arquivo.")
      .then((failure) => {
        setError(failure);
        if (failure === null) setNotice(`${file.name} enviado. A indexação começa em seguida.`);
      })
      .finally(() => {
        setBusy(false);
        input.value = "";
      });
  }

  return (
    <div className="stack">
      <label className="field">
        Arquivo (PDF, Markdown, TXT ou DOCX, até 20 MB)
        <input type="file" accept={ACCEPT} disabled={busy} onChange={choose} />
      </label>
      <FormMessage error={error} notice={notice} />
    </div>
  );
}
