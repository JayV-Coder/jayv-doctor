# Mockups (mobile first)

Canvas com as 26 telas: **[Integration AI Doctor — Mockups mobile first](https://claude.ai/artifact/KJnu4pFdbtiZgkuayGRpXz)**. O link é privado até ser compartilhado pelo menu Share do canvas.

Base: 390 × 844 (celular), com variantes desktop (≥ 1280 px) do Dashboard e do Incidente. Cada tela tem a opção de tema escuro; o app segue o sistema ou a escolha em Mais.

| # | Tela | Tickets |
|---|---|---|
| 1 | Login e MFA | 04 |
| 2 | Criar organização | 05 |
| 3 | Seletor de organização | 05 |
| 4 | Dashboard executivo (+ desktop) | 21 |
| 5 | Incidentes | 20 |
| 6 | Incidente e diagnóstico (+ desktop) | 20, 25, 26 |
| 7 | Explorador de execuções | 19 |
| 8 | Timeline da execução | 19 |
| 9 | Evento original | 19 |
| 10 | Integrações | 10 |
| 11 | Conectores | 16 |
| 12 | Conector GCP (wizard) | 16 |
| 13 | Importar logs | 11 |
| 14 | Base de conhecimento | 23 |
| 15 | Membros e convites | 06 |
| 16 | Mais · Retenção e LGPD | 29 |
| 17 | Uso e cotas | 31 |
| 18 | Auditoria | 28 |
| 19 | Relatório técnico | 32 |
| 20 | Alertas e notificações (v0.3) | 41 |
| 21 | ITSM (v0.3) | 43, 44 |
| 22 | Planos e cobrança (v1.0) | 50 |
| 23 | SSO corporativo (v1.0) | 48, 49 |

Tokens visuais (kit v2, linguagem JayV): fundo `#f4f4f0`, superfície `#ffffff`, secundária `#eaeae5`, borda `#d8d8d2`, texto `#161616`, secundário `#63635f` (mais escuro que o `#6c6c68` do kit, para passar no contraste AA), acento `#dfff5f`, ok `#23874a`, atenção `#b07a06`, erro `#d13a26`, info `#2f5f9e`. Tema escuro: fundo `#111210`, superfície `#1b1c19`, texto `#f4f4f0`. Fonte IBM Plex Mono. Alvos de toque ≥ 44 px. No código, os tokens ficam em `apps/web/src/app/globals.css` e os componentes base em `apps/web/src/components/ui` ([ADR-0010](../adr/0010-kit-css-do-mockup-e-dados-no-servidor.md)).
