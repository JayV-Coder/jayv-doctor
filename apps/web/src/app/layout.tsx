import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Integration AI Doctor",
  description: "Diagnóstico auditável de integrações SAP, Salesforce e Google Cloud.",
};

// `resizes-content`: o teclado virtual encolhe a página em vez de cobrir o formulário.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  interactiveWidget: "resizes-content",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR" className={mono.variable}>
      <body>{children}</body>
    </html>
  );
}
