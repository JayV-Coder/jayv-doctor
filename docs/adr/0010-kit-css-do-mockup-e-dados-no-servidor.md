# Kit CSS do mockup, dados no servidor e formatação com Intl no app web

O PRD e o ticket #9 citam Tailwind, shadcn/ui, `next-intl` e React Query. O app web segue outro caminho, por três motivos.

**Estilo.** O canvas de mockups passou para o kit v2 (linguagem visual JayV: IBM Plex Mono, fundo `#f4f4f0`, acento `#dfff5f`, tema escuro equivalente), escrito como um kit de classes CSS com tokens em variáveis. As telas dos tickets #4 a #6 já usam esse kit em `apps/web/src/app/globals.css`. Portar para Tailwind e trocar os componentes por shadcn/ui (Radix) reescreveria telas prontas, sem ganho visual, e afastaria o código do mockup, que é a referência de UI. Os componentes base ficam em `apps/web/src/components/ui`, sobre o mesmo kit; diálogos e a folha inferior usam o `<dialog>` nativo, que já prende o foco e fecha com Esc.

**Dados.** As telas são Server Components que chamam a API no servidor, com o token tirado do cookie da sessão (`lib/api.ts`). Não há cache de dados no navegador. Isso também simplifica uma regra de segurança do PWA: depois do logout, nada de tenant fica guardado no aparelho, porque o service worker só guarda a tela offline e os arquivos estáticos do build. React Query entra quando surgir a primeira tela que precise buscar dados no cliente (polling da lista de Execuções ou status de Diagnóstico em tempo real), e então o cache precisa ser limpo no logout e na troca de Organização.

**Idioma.** O PRD prevê só pt-BR. Os textos ficam no código, e números, porcentagens e datas passam por `Intl` em `lib/format.ts` (horário no fuso do navegador). Um catálogo de mensagens (`next-intl`) só faz sentido quando houver um segundo idioma no roadmap.

Vale rever esta decisão se o time de front crescer e preferir utilitários, ou se um segundo idioma entrar no roadmap.
