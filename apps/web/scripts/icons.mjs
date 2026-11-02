// Gera os ícones PNG do PWA a partir do desenho abaixo: `node scripts/icons.mjs`.
// Usa o Chromium do Playwright, que já é dependência dos testes E2E.
import { writeFile } from "node:fs/promises";
import { chromium } from "@playwright/test";

const CHEVRON = "M196 148 L316 256 L196 364";

function svg({ size, maskable }) {
  // Maskable: o sistema recorta até 20% de cada lado, então o desenho encolhe para a zona segura.
  const scale = maskable ? 0.6 : 0.8;
  const offset = ((512 * (1 - scale)) / 2).toFixed(1);
  const radius = maskable ? 0 : 96;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="${radius}" fill="#161616"/>
  <g transform="translate(${offset} ${offset}) scale(${scale})">
    <path d="${CHEVRON}" fill="none" stroke="#dfff5f" stroke-width="56" stroke-linecap="square"/>
  </g>
</svg>`;
}

const ICONS = [
  { file: "icon-192.png", size: 192, maskable: false },
  { file: "icon-512.png", size: 512, maskable: false },
  { file: "maskable-512.png", size: 512, maskable: true },
  { file: "apple-touch-icon.png", size: 180, maskable: true },
];

const browser = await chromium.launch();
const page = await browser.newPage();
for (const { file, size, maskable } of ICONS) {
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(`<body style="margin:0">${svg({ size, maskable })}</body>`);
  await page.locator("svg").screenshot({ path: `public/icons/${file}`, omitBackground: true });
}
await browser.close();
// Favicon: o Next publica `src/app/icon.svg` e põe o <link> no <head>.
await writeFile("src/app/icon.svg", `${svg({ size: 32, maskable: false })}\n`);
