# Fator de reserva em vez de códigos de recuperação

O ticket #4 pede códigos de recuperação de MFA, mas o Supabase Auth não os oferece: uma sessão só chega a `aal2` verificando um fator. Códigos próprios exigiriam um caminho nosso para elevar a sessão com `service_role` ou remover fatores, fora do Auth, e esse caminho seria um desvio do MFA, com superfície de ataque própria. Por isso a recuperação é um segundo fator TOTP, cadastrado em `/seguranca`, em outro aparelho; a tela de cadastro leva a ela logo depois do primeiro fator.

Quem perde todos os fatores depende de um operador da plataforma, que remove os fatores pela API administrativa do Auth depois de confirmar a identidade da pessoa. Esse procedimento ainda precisa entrar no runbook de suporte. Se o Auth passar a oferecer códigos de recuperação, esta decisão deve ser revista.
