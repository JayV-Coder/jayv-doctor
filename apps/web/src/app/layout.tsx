import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import { cookies } from "next/headers";
import type { ReactNode } from "react";
import { ServiceWorker } from "@/components/shell/service-worker";
import { parseTheme, THEME_COOKIE } from "@/lib/shell/theme";
import "./globals.css";

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Integration AI Doctor",
  description: "Diagnóstico auditável de integrações SAP, Salesforce e Google Cloud.",
  applicationName: "Integration AI Doctor",
  appleWebApp: { capable: true, title: "AI Doctor", statusBarStyle: "default" },
  icons: { apple: "/icons/apple-touch-icon.png" },
};

// `resizes-content`: o teclado virtual encolhe a página em vez de cobrir o formulário.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  interactiveWidget: "resizes-content",
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f4f0" },
    { media: "(prefers-color-scheme: dark)", color: "#111210" },
  ],
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const theme = parseTheme((await cookies()).get(THEME_COOKIE)?.value);

  return (
    <html
      lang="pt-BR"
      className={mono.variable}
      data-theme={theme === "system" ? undefined : theme}
    >
      <body>
        {children}
        <ServiceWorker />
      </body>
    </html>
  );
}
