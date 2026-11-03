"use client";

import { REALTIME_SUBSCRIBE_STATES } from "@supabase/supabase-js";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

// Tempo real dos Diagnósticos do Incidente (ADR-0005): qualquer versão nova ou mudança de etapa,
// pedida aqui, por um colega ou pelo automático, busca a página de novo. Enquanto o canal não
// conecta e há Diagnóstico rodando, a reserva é buscar a cada 5 s.
export function DiagnosisLive({ incidentId, active }: { incidentId: string; active: boolean }) {
  const router = useRouter();
  const [subscribed, setSubscribed] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const channel = supabase
      .channel(`doctor-diagnoses-${incidentId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "doctor",
          table: "diagnoses",
          filter: `incident_id=eq.${incidentId}`,
        },
        () => {
          clearTimeout(timer);
          timer = setTimeout(() => {
            router.refresh();
          }, 800);
        },
      )
      .subscribe((status) => {
        setSubscribed(status === REALTIME_SUBSCRIBE_STATES.SUBSCRIBED);
      });
    return () => {
      clearTimeout(timer);
      void supabase.removeChannel(channel);
    };
  }, [router, incidentId]);

  useEffect(() => {
    if (!active || subscribed) return;
    const poll = setInterval(() => {
      router.refresh();
    }, 5000);
    return () => {
      clearInterval(poll);
    };
  }, [active, subscribed, router]);

  return null;
}
