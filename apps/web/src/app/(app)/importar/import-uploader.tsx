"use client";

import { useState, type ChangeEvent } from "react";
import { FormMessage } from "@/components/auth-shell";
import type { Integration } from "@/lib/api";
import { environmentLabel } from "@/lib/integrations/labels";
import { completeImport, createImport } from "./actions";

const ACCEPT = ".json,.ndjson,.csv";

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

// O arquivo vai direto do navegador para o Storage, pela URL assinada: não passa pela API.
function put(url: string, file: File, onProgress: (ratio: number) => void): Promise<boolean> {
  return new Promise((resolve) => {
    const request = new XMLHttpRequest();
    request.open("PUT", url);
    request.setRequestHeader("content-type", file.type || "application/octet-stream");
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    request.onload = () => {
      resolve(request.status >= 200 && request.status < 300);
    };
    request.onerror = () => {
      resolve(false);
    };
    request.send(file);
  });
}

export function ImportUploader({ integrations }: { integrations: Integration[] }) {
  const [integrationId, setIntegrationId] = useState(integrations[0]?.id ?? "");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function send(file: File) {
    setError(null);
    setProgress(0);
    const { created, error: refused } = await createImport({
      integration_id: integrationId,
      filename: file.name,
      size_bytes: file.size,
      sha256: await sha256(file),
    }).catch(() => ({ created: null, error: "Sem conexão. Tente de novo." }));
    // Recusa (formato, tamanho, duplicada) já aparece na lista, com o motivo.
    if (!created?.upload_url) {
      setError(refused);
      setProgress(null);
      return;
    }
    const uploaded = await put(created.upload_url, file, setProgress);
    setError(
      uploaded
        ? await completeImport(created.id).catch(() => "Sem conexão. Tente de novo.")
        : "O envio do arquivo falhou. Tente de novo.",
    );
    setProgress(null);
  }

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (file) void send(file).finally(() => (input.value = ""));
  }

  return (
    <div className="stack">
      <label className="field">
        Integração
        <select
          value={integrationId}
          onChange={(event) => {
            setIntegrationId(event.target.value);
          }}
        >
          {integrations.map((integration) => (
            <option key={integration.id} value={integration.id}>
              {integration.name} · {environmentLabel(integration.environment)}
            </option>
          ))}
        </select>
      </label>
      <label className="drop">
        <svg
          viewBox="0 0 24 24"
          width="28"
          height="28"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          aria-hidden="true"
        >
          <path d="M12 16V4M7 9l5-5 5 5M4 20h16" />
        </svg>
        <strong>Escolher arquivo</strong>
        <span className="small">JSON, NDJSON ou CSV · até 50 MB</span>
        <input
          className="visually-hidden"
          type="file"
          accept={ACCEPT}
          disabled={progress !== null}
          onChange={choose}
        />
      </label>
      {progress !== null && (
        <div className="confidence" role="status" aria-label="Enviando arquivo">
          <span className="small">Enviando… {Math.round(progress * 100)}%</span>
          <div className="confidence-track">
            <i style={{ width: `${String(Math.round(progress * 100))}%` }} />
          </div>
        </div>
      )}
      <FormMessage error={error} />
    </div>
  );
}
