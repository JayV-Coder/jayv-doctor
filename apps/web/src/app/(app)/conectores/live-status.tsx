"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { createClient } from "@/lib/supabase/client";

// Status em tempo real: o Realtime avisa que um Conector mudou e a página busca de novo na API.
// O evento passa pelo RLS e pelos privilégios de coluna de quem assina, mas o conteúdo dele nem é
// usado: a fonte da tela continua sendo a API.
export function LiveStatus() {
  const router = useRouter();

  useEffect(() => {
    const supabase = createClient();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const channel = supabase
      .channel("doctor-connectors")
      .on("postgres_changes", { event: "*", schema: "doctor", table: "connectors" }, () => {
        // Uma Sincronização muda a linha algumas vezes seguidas: uma busca só.
        clearTimeout(timer);
        timer = setTimeout(() => {
          router.refresh();
        }, 800);
      })
      .subscribe();
    return () => {
      clearTimeout(timer);
      void supabase.removeChannel(channel);
    };
  }, [router]);

  return null;
}
