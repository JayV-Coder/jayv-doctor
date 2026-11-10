# Alertas e notificações (worker `notifier`)

Decisões em [ADR-0017](../adr/0017-alertas-por-worker-proprio.md); rotas em [docs/api/alerts.md](../api/alerts.md). A Tela 20 fica em **Mais → Alertas**.

## Fluxo

1. Incidente aberto ou atualizado e Conector em `failing` gravam `alert.evaluate` na outbox, por trigger, na mesma transação, se a Organização tem Regra ligada do tipo.
2. O relay publica (rodada de 40 s por minuto, olhando a outbox a cada 2 s) e o `notifier` avalia as Regras ligadas da Organização.
3. A cada minuto, `POST /alerts/scan` (`aid-…-alerts-scan`) avalia taxa de erro e Diagnóstico aguardando revisão.
4. Para cada Regra que casa: lock por assunto, no máximo uma entrega por canal e assunto a cada 15 min (canal com falha espera 5 min), silêncio da Regra e de cada Usuário (crítico fura), e entrega em cada canal. Tudo fica em `notification_deliveries` (`pending`, `sent`, `failed`, `suppressed`, `quiet`), que só gestores leem, por 30 dias.

## Canais

| Canal | Como entrega | Configuração |
|---|---|---|
| Push no PWA | Web Push com VAPID (`pywebpush`) para os aparelhos do público; assinatura que o serviço diz não existir mais (404/410) é apagada | `AID_VAPID_PRIVATE_KEY` (segredo `vapid-private-key`) no `notifier`, `AID_VAPID_PUBLIC_KEY` (tfvars `vapid_public_key`) na API, `AID_VAPID_SUBJECT` |
| E-mail | SMTP (`SMTP_URL`, o mesmo dos avisos de Cota) para o público | `audience`: gestores ou todos |
| Slack | POST no Incoming Webhook, texto com o link | webhook no Vault |
| Microsoft Teams | POST de um Adaptive Card no Incoming Webhook ou no Workflows | webhook no Vault |

Gerar as chaves VAPID uma vez por ambiente:

```sh
uv run python -c "from py_vapid import Vapid02; v = Vapid02(); v.generate_keys(); \
  import base64; from cryptography.hazmat.primitives import serialization as s; \
  print('privada:', v.private_pem().decode()); \
  print('pública:', base64.urlsafe_b64encode(v.public_key.public_bytes(s.Encoding.X962, s.PublicFormat.UncompressedPoint)).decode().rstrip('='))"
```

A privada vai para o Secret Manager (`vapid-private-key`), em PEM como sai daqui (o `notifier` também aceita DER em base64); a pública, para `vapid_public_key` no tfvars. Trocar as chaves invalida as assinaturas existentes: cada Usuário ativa o push de novo.

## Conteúdo

Só título, severidade, Integração, Ambiente e link. Nunca log, Evidência, Referência de negócio ou mensagem de erro do sistema do cliente.
