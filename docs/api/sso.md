# SSO corporativo (SAML 2.0) e SCIM

Ticket #48, [ADR-0021](../adr/0021-sso-saml-pelo-supabase-auth.md). Configurar é do Owner com `aal2`; as rotas que mudam algo aceitam `Idempotency-Key`.

| Rota | Efeito |
|---|---|
| `GET /api/v1/sso` | `{ connection, domains, groups }`. `connection` traz `status` (`pending_platform`, `active`, `error`), `metadata_url`, `require_sso`, `default_role`, `last_error` e `scim_enabled`; cada domínio traz `txt_name` e `txt_value` para o DNS |
| `PUT /api/v1/sso` | `{ metadata_url, require_sso, default_role }` cria ou atualiza a conexão e pede o registro à plataforma. `require_sso` sem domínio verificado → `422 domain_required` |
| `DELETE /api/v1/sso` | Desliga o SSO e remove o provedor → `204` |
| `POST /api/v1/sso/domains` | `{ domain }` → `201` com o TXT a publicar. Repetido na Organização, ou já verificado por outra → `409 domain_taken`. Cadastrar não reserva o domínio: fica com ele quem verificar primeiro |
| `POST /api/v1/sso/domains/{id}/verify` | Pede a consulta ao DNS → `202`; a tela acompanha pelo `verified_at` |
| `DELETE /api/v1/sso/domains/{id}` | Remove o domínio; sem domínio verificado, "Exigir SSO" desliga → `204` |
| `PUT /api/v1/sso/groups` | `{ groups: { "<grupo do IdP>": "admin" \| "analyst" \| "viewer" } }` substitui o mapeamento |
| `POST /api/v1/sso/scim-token` | Token SCIM novo → `{ token, base_url }`. Aparece só aqui; o anterior deixa de valer |
| `POST /api/v1/sso/provision` | Logo depois do login pelo IdP (JWT com `amr` de SSO, sem Organização): cria ou ajusta o Vínculo e ativa a Organização → `{ tenant_id, role }`. A web renova a sessão em seguida. Os grupos vêm da identidade que o IdP gravou no Auth, nunca do perfil editável. Erros: `409 plan_limit` (gente nova com a Organização no limite de membros), `403 sso_inactive`, `sso_deactivated` (desativado no IdP pelo SCIM), `sso_no_group` (sem grupo mapeado nem Papel padrão; o Vínculo que havia é removido, menos o do Owner) |
| `GET /api/v1/sso/discover?email=` | Sem sessão, com limite por IP: `{ sso, required, domain }` para a tela de login |

Com o Vínculo removido (SCIM ou tela), toda rota com Organização responde `401 membership_revoked`, mesmo com o JWT ainda válido.

## SCIM 2.0

Base: `https://<API>/scim/v2`, com `Authorization: Bearer <token SCIM>`. Respostas em `application/scim+json`.

| Rota | Efeito |
|---|---|
| `GET /ServiceProviderConfig` | Suporte: PATCH e filtro; sem bulk, sort, etag e troca de senha |
| `GET /Users?filter=userName eq "<e-mail>"&startIndex=1&count=100` | `ListResponse` em páginas de até 100, com o `totalResults` da lista inteira; só esse filtro é aceito (`400 invalidFilter`) |
| `GET /Users/{id}` | O Usuário |
| `POST /Users` | `{ userName, externalId?, active? }` → `201`; `userName` é o e-mail. Repetido → `409 uniqueness` |
| `PUT /Users/{id}` | Só `active` vale |
| `PATCH /Users/{id}` | `Operations` com `replace` de `active`, pelo `path` (Entra ID) ou no objeto `value` (Okta) |
| `DELETE /Users/{id}` | Apaga e tira o acesso → `204` |

Desativar ou apagar remove o Vínculo do Doctor (o do Owner fica) de toda conta com aquele e-mail. As sessões no Supabase Auth só são apagadas quando o e-mail é de um domínio verificado da Organização e havia Vínculo: elas valem para o projeto inteiro, e o token SCIM de uma Organização não desloga quem não é dela. A linha de `public.organization_members` fica. Token errado → `401` no formato de erro do SCIM.
