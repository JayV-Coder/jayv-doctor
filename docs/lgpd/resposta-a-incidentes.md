# Resposta a incidente de segurança com dado pessoal

## Papéis

- **Responsável pelo incidente:** quem estiver de plantão no Doctor; aciona o encarregado (DPO) e o responsável técnico.
- **Encarregado (DPO):** decide a comunicação à ANPD e aos controladores.

## Passos

1. **Detectar e registrar** (hora zero): alerta, relato de cliente ou achado interno. Abrir o registro do incidente com hora, fonte e o que se sabe.
2. **Conter** (até 4 h): revogar tokens e chaves afetados (tokens de ingestão, chave de serviço, credenciais de Conector no Vault), bloquear o acesso suspeito, pausar Conectores se preciso.
3. **Avaliar** (até 24 h): quais Organizações, quais dados e quantos titulares. Fontes: a Trilha de auditoria (`audit_logs`, com IP, user agent e request id), os logs do Cloud Run e do Supabase, e a matriz de isolamento (para descartar falha de RLS).
4. **Comunicar o controlador** (até 24 h depois de confirmado, pelo DPA): o que aconteceu, dados e titulares afetados, medidas tomadas e o contato.
5. **ANPD e titulares:** o controlador comunica a ANPD e os titulares quando o incidente pode acarretar risco ou dano relevante, em até 3 dias úteis (Resolução CD/ANPD nº 15/2024); o operador fornece as informações que tiver.
6. **Corrigir e aprender:** causa raiz, teste que reproduz o problema (inclusive na suíte de isolamento, se for o caso), postmortem sem culpados e revisão do RIPD.

## Contatos

| Quem | Como |
|---|---|
| Plantão do Doctor | [canal de plantão] |
| Encarregado (DPO) | [e-mail do encarregado] |
| Supabase | Suporte do plano contratado |
| Google Cloud | Suporte do projeto |
