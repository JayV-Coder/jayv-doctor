"use client";

import { useEffect, useState, useTransition } from "react";
import { FormMessage } from "@/components/auth-shell";
import { Chip } from "@/components/ui/chip";
import { applicationServerKey, quietText, type Quiet } from "@/lib/alerts/labels";
import { saveQuiet, subscribePush, unsubscribePush } from "./actions";
import { useIdempotencyKey } from "./use-key";

type Subscription = { id: string; endpoint: string };
type State = "unsupported" | "unknown" | "denied" | "on" | "off";

// "Meus canais": o push deste aparelho e o silêncio fora do plantão (Tela 20).
export function MyChannels({
  pushKey,
  subscriptions,
  quiet,
}: {
  pushKey: string | null;
  subscriptions: Subscription[];
  quiet: Quiet;
}) {
  const [state, setState] = useState<State>("unknown");
  const [endpoint, setEndpoint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const [key, settle] = useIdempotencyKey();

  useEffect(() => {
    if (!pushKey || !("serviceWorker" in navigator) || !("PushManager" in window)) {
      setState("unsupported");
      return;
    }
    if (Notification.permission === "denied") {
      setState("denied");
      return;
    }
    void navigator.serviceWorker.getRegistration().then(async (registration) => {
      const current = await registration?.pushManager.getSubscription();
      const known = current && subscriptions.some((item) => item.endpoint === current.endpoint);
      setEndpoint(current?.endpoint ?? null);
      setState(known ? "on" : "off");
    });
  }, [pushKey, subscriptions]);

  function enable() {
    startTransition(async () => {
      try {
        if ((await Notification.requestPermission()) !== "granted") {
          setState("denied");
          return;
        }
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: applicationServerKey(pushKey ?? ""),
        });
        const json = subscription.toJSON() as { keys?: { p256dh?: string; auth?: string } };
        const outcome = await subscribePush(
          {
            endpoint: subscription.endpoint,
            keys: { p256dh: json.keys?.p256dh ?? "", auth: json.keys?.auth ?? "" },
            user_agent: navigator.userAgent.slice(0, 300),
          },
          key(),
        );
        settle(outcome);
        setError(outcome.ok ? null : outcome.message);
        if (outcome.ok) {
          setEndpoint(subscription.endpoint);
          setState("on");
        }
      } catch {
        setError("O navegador não ativou o push. No iPhone, instale o app na tela de início.");
      }
    });
  }

  function disable() {
    const mine = subscriptions.find((item) => item.endpoint === endpoint);
    startTransition(async () => {
      const registration = await navigator.serviceWorker.getRegistration();
      await (await registration?.pushManager.getSubscription())?.unsubscribe();
      if (mine) {
        const outcome = await unsubscribePush(mine.id, key());
        settle(outcome);
        setError(outcome.ok ? null : outcome.message);
      }
      setState("off");
    });
  }

  return (
    <>
      <ul className="list" aria-label="Meus canais">
        <li>
          <div className="li">
            <span className="li-text">
              <span>Push neste dispositivo</span>
              {state === "denied" && (
                <span className="small">Bloqueado no navegador: libere nas configurações.</span>
              )}
              {state === "unsupported" && (
                <span className="small">
                  Indisponível aqui. No iPhone (iOS 16.4+), instale o app na tela de início.
                </span>
              )}
            </span>
            {state === "on" && (
              <button type="button" className="btn" disabled={busy} onClick={disable}>
                Desativar
              </button>
            )}
            {state === "off" && (
              <button type="button" className="btn primary" disabled={busy} onClick={enable}>
                Ativar
              </button>
            )}
            {state === "on" && <Chip tone="success">Ativo</Chip>}
          </div>
        </li>
      </ul>
      <form
        className="stack"
        aria-label="Silêncio fora do plantão"
        onSubmit={(event) => {
          // `onSubmit`, não `action`: o `action` limpa o formulário, e depois de um erro a
          // pessoa perderia o que digitou.
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          startTransition(async () => {
            const outcome = await saveQuiet(form, key());
            settle(outcome);
            setError(outcome.ok ? null : outcome.message);
          });
        }}
      >
        <p className="small">Silêncio fora do plantão: {quietText(quiet)}</p>
        <div className="grid2">
          <label className="field">
            Das
            <input name="quiet-start" type="time" defaultValue={quiet?.start ?? ""} />
          </label>
          <label className="field">
            Até
            <input name="quiet-end" type="time" defaultValue={quiet?.end ?? ""} />
          </label>
        </div>
        <button type="submit" className="btn" disabled={busy}>
          Salvar silêncio
        </button>
      </form>
      <FormMessage error={error} />
    </>
  );
}
