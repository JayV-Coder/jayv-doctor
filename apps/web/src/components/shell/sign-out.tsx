"use client";

// Sair cancela antes o push deste aparelho (#41): num navegador compartilhado, a tela de
// bloqueio não mostra mais os Incidentes de quem saiu. O serviço de push passa a recusar o
// endereço, e o `notifier` apaga a assinatura no próximo envio.
async function dropPush(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;
  const registration = await navigator.serviceWorker.getRegistration();
  await (await registration?.pushManager.getSubscription())?.unsubscribe();
}

export function SignOut() {
  return (
    <form
      action="/auth/sair"
      method="post"
      onSubmit={(event) => {
        event.preventDefault();
        const form = event.currentTarget;
        // No máximo 1 s esperando o navegador: sair nunca fica preso no push.
        void Promise.race([dropPush(), new Promise((done) => setTimeout(done, 1000))])
          .catch(() => undefined)
          .finally(() => {
            form.submit();
          });
      }}
    >
      <button className="btn" type="submit">
        Sair
      </button>
    </form>
  );
}
