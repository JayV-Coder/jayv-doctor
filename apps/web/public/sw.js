// Service worker do PWA. Guarda só o shell: a tela offline e os arquivos estáticos do build, que
// não carregam dado nenhum de tenant. Navegações e chamadas de dados vão sempre à rede; sem rede,
// a navegação recebe a tela offline. Assim, depois do logout nada de outra Organização aparece.
// A versão vem do build (`?v=` no registro): cada deploy instala um worker novo, que refaz o
// cache e apaga o anterior, então os estáticos de builds velhos não se acumulam.
const VERSION = new URL(self.location.href).searchParams.get("v") || "dev";
const CACHE = `shell-${VERSION}`;
const OFFLINE = "/offline";
const ICONS = ["/icons/icon-192.png", "/icons/icon-512.png"];

async function precache() {
  const cache = await caches.open(CACHE);
  const response = await fetch(OFFLINE, { cache: "no-store", credentials: "omit" });
  if (!response.ok) throw new Error(`offline: ${response.status}`);
  const html = await response.clone().text();
  await cache.put(OFFLINE, response);
  // CSS, fontes e scripts da própria tela offline, para ela abrir com o visual certo.
  const assets = new Set(html.match(/\/_next\/static\/[^"'\s)\\]+/g) ?? []);
  await Promise.all([...assets, ...ICONS].map((url) => cache.add(url).catch(() => undefined)));
}

// Se o navegador tiver despejado o cache, ainda assim responde "Sem conexão", e não um erro de rede.
async function offline() {
  const page = await caches.match(OFFLINE);
  return (
    page ??
    new Response('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><h1>Sem conexão</h1>', {
      status: 503,
      headers: { "content-type": "text/html; charset=utf-8" },
    })
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(precache().then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(offline));
    return;
  }
  // Nome com hash do build: o conteúdo nunca muda, e é igual para todo mundo.
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ??
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              event.waitUntil(caches.open(CACHE).then((cache) => cache.put(request, copy)));
            }
            return response;
          }),
      ),
    );
  }
});

// Push dos alertas (#41): o servidor manda só título, corpo curto e o link do Incidente.
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {};
  }
  const title = typeof data.title === "string" ? data.title : "Integration AI Doctor";
  const url = typeof data.url === "string" ? data.url : "/";
  event.waitUntil(
    self.registration.showNotification(title, {
      body: typeof data.body === "string" ? data.body : "",
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: url,
      data: { url },
    }),
  );
});

// Só abre caminho do próprio app: o link vem do servidor, mas a notificação não navega para fora.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/", self.location.origin);
  const url = target.origin === self.location.origin ? target.pathname + target.search : "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const open = windows.find((client) => new URL(client.url).origin === self.location.origin);
      if (open) return open.navigate(url).then((client) => (client ?? open).focus());
      return self.clients.openWindow(url);
    }),
  );
});
