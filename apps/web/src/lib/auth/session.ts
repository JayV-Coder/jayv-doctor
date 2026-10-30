import type { SessionState } from "./gate";

interface Levels {
  currentLevel: string | null;
  nextLevel: string | null;
}

// `claims` vem do JWT verificado; o Papel é a claim do Custom Access Token Hook.
export function toSessionState(
  claims: Record<string, unknown> | null,
  levels: Levels | null,
): SessionState {
  const role = claims?.tenant_role;
  return {
    hasSession: claims !== null,
    role: typeof role === "string" ? role : null,
    currentLevel: levels?.currentLevel ?? null,
    nextLevel: levels?.nextLevel ?? null,
  };
}
