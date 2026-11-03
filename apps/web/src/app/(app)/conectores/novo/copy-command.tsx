"use client";

import { useState } from "react";

export function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="cmd">
      <code>{command}</code>
      <button
        type="button"
        className="btn"
        onClick={() => {
          void navigator.clipboard.writeText(command).then(() => {
            setCopied(true);
          });
        }}
      >
        {copied ? "Copiado" : "Copiar"}
      </button>
    </div>
  );
}
