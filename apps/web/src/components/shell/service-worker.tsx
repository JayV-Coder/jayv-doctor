"use client";

import { useEffect } from "react";

// Só em produção: no `next dev` o cache do shell atrapalharia o recarregamento.
export function ServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => undefined);
  }, []);
  return null;
}
