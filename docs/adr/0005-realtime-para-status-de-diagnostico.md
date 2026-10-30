# Supabase Realtime no lugar de SSE para o status do Diagnóstico

O PRD previa SSE ou polling para acompanhar o diagnóstico assíncrono. Usamos o Supabase Realtime (`postgres_changes` na tabela `diagnoses`), que já respeita o RLS e funciona igual no navegador móvel e no PWA. Com isso a API não precisa manter conexões abertas no Cloud Run, onde conexões longas custam caro e são encerradas por timeout. Como fallback, o cliente faz polling em `GET /api/v1/diagnoses/{id}` a cada 5 s se o canal cair.
