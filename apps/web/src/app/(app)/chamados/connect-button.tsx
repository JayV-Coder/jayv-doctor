"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { connectJira } from "./actions";

export function ConnectJira({ label }: { label: string }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  return (
    <>
      <button
        type="button"
        className="btn primary"
        disabled={busy}
        onClick={() => {
          startTransition(async () => {
            setError(await connectJira());
          });
        }}
      >
        {label}
      </button>
      <FormMessage error={error} />
    </>
  );
}
