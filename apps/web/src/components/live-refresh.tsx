"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { createClient } from "@/lib/supabase/client";

// Tempo real: o Realtime avisa que a tabela mudou e a página busca de novo na API. O evento passa
// pelo RLS e pelos privilégios de coluna de quem assina; o conteúdo dele nem é usado.
export function LiveRefresh({ table, id }: { table: string; id?: string }) {
  const router = useRouter();

  useEffect(() => {
    const supabase = createClient();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const channel = supabase
      .channel(id ? `doctor-${table}-${id}` : `doctor-${table}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "doctor", table, ...(id && { filter: `id=eq.${id}` }) },
        () => {
          // Várias mudanças seguidas viram uma busca só.
          clearTimeout(timer);
          timer = setTimeout(() => {
            router.refresh();
          }, 800);
        },
      )
      .subscribe();
    return () => {
      clearTimeout(timer);
      void supabase.removeChannel(channel);
    };
  }, [router, table, id]);

  return null;
}
