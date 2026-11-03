"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// Reserva do Realtime (ADR-0005): enquanto o Diagnóstico roda, busca de novo a cada 5 s.
export function PollWhileActive({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => {
      router.refresh();
    }, 5000);
    return () => {
      clearInterval(timer);
    };
  }, [active, router]);
  return null;
}
