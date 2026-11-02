import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import type { ReactNode } from "react";
import { ServiceWorker } from "@/components/shell/service-worker";
import { THEME_COLORS, THEME_SCRIPT } from "@/lib/shell/theme";
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
    { media: "(prefers-color-scheme: light)", color: THEME_COLORS.light },
    { media: "(prefers-color-scheme: dark)", color: THEME_COLORS.dark },
  ],
};

// `suppressHydrationWarning`: o script do tema muda o <html> antes de o React assumir a página.
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR" className={mono.variable} suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        {children}
        <ServiceWorker />
      </body>
    </html>
  );
}
