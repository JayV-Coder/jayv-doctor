"use client";

import { useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { addComment } from "../actions";

export function CommentForm({ id }: { id: string }) {
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();

  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        startTransition(async () => {
          const failure = await addComment(id, body, []).catch(() => "Sem conexão. Tente de novo.");
          setError(failure);
          if (failure === null) setBody("");
        });
      }}
    >
      <label className="field">
        Comentário
        <textarea
          rows={3}
          maxLength={4000}
          required
          value={body}
          onChange={(event) => {
            setBody(event.currentTarget.value);
          }}
        />
      </label>
      <FormMessage error={error} />
      <button className="btn" type="submit" disabled={busy || body.trim() === ""}>
        Comentar
      </button>
    </form>
  );
}
