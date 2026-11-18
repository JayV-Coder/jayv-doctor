# Organizações do jayv-coder aparecem no Doctor

Quem já tem Organização no jayv-coder não cria outra para usar o Doctor. Ela aparece no Doctor, e o owner de lá ativa o produto só com o que é do Doctor: segmento, perfil de IA e o aceite do DPA. Nome e identificador continuam os do jayv-coder. Revisa o [ADR-0009](0009-doctor-no-projeto-supabase-do-jayv-coder.md): estar em `public.organization_members` passa a dar acesso ao Doctor quando ele está ativo na Organização.

- **`doctor.available_organizations()`:** as Organizações do jayv-coder de quem pede, ainda sem linha em `doctor.tenants`. O `/me` as devolve em `available_organizations`.
- **`doctor.enable_organization(org, segmento, provedor)`:** só o owner do jayv-coder ativa. Quem não é da Organização recebe 404, como recurso de outra Organização. Grava `doctor.tenants`, dá o Vínculo a todos os membros e deixa a Organização ativa para quem ativou.
- **Papel equivalente:**

  | jayv-coder | Doctor |
  |---|---|
  | owner | Owner |
  | maintainer | Admin |
  | member | Viewer |

  Depois, o Owner do Doctor muda o Papel quando quiser.
- **`doctor.join_organizations()`**, a cada `/me`: quem entrou no jayv-coder depois da ativação ganha o Vínculo no próximo acesso.
- **Remoção:** quem o Doctor removeu fica em `doctor.membership_removals`, e o acesso automático não o devolve. Um convite aceito devolve. Quem sai do jayv-coder perde o acesso ao Doctor, pela FK do Vínculo.

Criar uma Organização nova continua possível na mesma página do site (`/doctor/organizations`), abaixo das que já existem.

## Consequências

- **O Papel no jayv-coder só vale na entrada.** Uma mudança de Papel lá depois da ativação não muda o Papel no Doctor.
- **A ativação é do owner porque o aceite do DPA é dele.** O maintainer vê a Organização, mas não a ativa.
- **Organização suspensa no Doctor** não dá Vínculo novo.

## Considered Options

- **O owner escolhe quem entra:** mais controle, mas a Organização já tem a lista de membros, e o Owner pode mudar Papéis ou remover depois.
- **Criar Organização só no jayv-coder:** o site restringe a criação de Organizações a alguns planos, e o Doctor tem clientes fora deles.
