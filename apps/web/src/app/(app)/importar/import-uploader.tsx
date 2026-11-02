"use client";

import { createSHA256 } from "hash-wasm";
import { useState, type ChangeEvent } from "react";
import { FormMessage } from "@/components/auth-shell";
import type { Integration } from "@/lib/api";
import { environmentLabel } from "@/lib/integrations/labels";
import { completeImport, createImport, requestUploadUrl } from "./actions";

const ACCEPT = ".json,.ndjson,.csv";

const FAILED = "Não foi possível ler ou enviar o arquivo. Tente de novo.";

// Em blocos: um arquivo de 50 MB não fica inteiro na memória de um celular.
async function sha256(file: File): Promise<string> {
  const hasher = await createSHA256();
  const reader = file.stream().getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return hasher.digest("hex");
    hasher.update(value);
  }
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

  // Devolve a mensagem de erro, ou `null`. Recusa (formato, tamanho, duplicada) não é erro aqui:
  // a Importação aparece na lista com o motivo.
  async function upload(file: File): Promise<string | null> {
    const { created, error } = await createImport({
      integration_id: integrationId,
      filename: file.name,
      size_bytes: file.size,
      sha256: await sha256(file),
    });
    if (!created || created.status !== "pending") return error;
    const { url, error: unsigned } = await requestUploadUrl(created.id);
    if (!url) return unsigned;
    if (!(await put(url, file, setProgress))) return "O envio do arquivo falhou. Tente de novo.";
    return completeImport(created.id);
  }

  async function send(file: File) {
    setError(null);
    setProgress(0);
    try {
      setError(await upload(file));
    } catch {
      // Arquivo ilegível depois de escolhido, ou rede fora: o seletor volta a funcionar.
      setError(FAILED);
    } finally {
      setProgress(null);
    }
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
