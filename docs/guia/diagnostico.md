# Lendo um Diagnóstico

Um **Incidente** reúne Execuções com a mesma falha, na mesma Integração, numa janela de 30 min. Abra o Incidente e use **Novo diagnóstico** → **Diagnosticar**. Há dois modos:

- **Híbrido:** Regras, Base de conhecimento e IA. É o padrão.
- **Só Regras (sem IA):** nenhum dado vai para o modelo de linguagem.

O progresso aparece no card, etapa a etapa.

## O que o card mostra

- **Causa provável** e o **sistema responsável**, com a **Confiança, sempre "heurística"**: uma estimativa do motor, não uma probabilidade calibrada.
- **Evidências:** cada uma aponta para um registro real (um Evento, um trecho de log, uma Regra ou um documento da Base). Toque para abrir o Evento original.
- **Hipóteses** alternativas, em ordem.
- **Recomendações:** sempre ações para uma pessoa fazer. O Doctor não executa nada.
- **Inconclusivo:** quando as Evidências não bastam, o Diagnóstico diz isso e lista o que coletar, em vez de afirmar uma causa.
- **Só com as Regras:** se o envio ao LLM estiver desligado na Organização ou a Cota de IA do mês tiver acabado, o card avisa o motivo.

## Revisar

A revisão melhora o Doctor e mede a precisão no piloto. No card, escolha **Aceitar**, **Corrigir** (com a **Categoria correta** ou a **Causa correta**) ou **Rejeitar**, com um **Comentário** opcional. Um Diagnóstico publicado não muda: uma nova análise é uma nova versão.

Resolvido o Incidente (**Mudar status** → resolvido, com a **Nota de resolução**), **Promover à Base de conhecimento** transforma o caso em referência para os próximos Diagnósticos.

## Relatório técnico

**Relatório** gera um PDF ou Markdown do Incidente e do Diagnóstico atual, para outra equipe. Ele traz a Confiança com o rótulo heurístico, as Evidências com os ids, as Recomendações e a revisão, opcionalmente com a timeline e trechos sanitizados. **Compartilhar link** cria um link de 7 dias, que pode ser revogado e tem cada acesso registrado na Trilha de auditoria.
