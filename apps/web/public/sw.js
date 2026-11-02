// Service worker do PWA. Guarda só o shell: a tela offline e os arquivos estáticos do build, que
// não carregam dado nenhum de tenant. Navegações e chamadas de dados vão sempre à rede; sem rede,
// a navegação recebe a tela offline. Assim, depois do logout nada de outra Organização aparece.
const CACHE = "shell-v1";
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
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE)));
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
