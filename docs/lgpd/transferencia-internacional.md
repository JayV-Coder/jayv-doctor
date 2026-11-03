# Transferência internacional

| Subprocessador | O que recebe | Onde | Salvaguarda |
|---|---|---|---|
| Supabase | Banco, arquivos, autenticação | Região do projeto (conferir na janela de configuração) | Cláusulas contratuais do Supabase (DPA) |
| Google Cloud | API, workers, filas, segredos, logs da plataforma | Brasil (southamerica-east1) | Sem transferência |
| Anthropic (padrão) | Evidências já sanitizadas, delimitadas, para a interpretação | Estados Unidos | DPA da Anthropic com cláusulas-padrão; sem uso para treino |
| Voyage AI (padrão) | Fragmentos sanitizados da Base de conhecimento e perguntas da busca | Estados Unidos | DPA da Voyage com cláusulas-padrão |
| Google Vertex AI (opcional) | O mesmo que Anthropic e Voyage | Brasil (southamerica-east1) | Sem transferência |

O controlador escolhe no cadastro da Organização entre Anthropic e Vertex AI (São Paulo) e pode desligar o envio ao LLM a qualquer momento (Mais › LGPD e IA). Desligado, nenhum dado da Organização vai a provedor de IA: o Diagnóstico usa só as Regras e a Base de conhecimento busca só pelo texto.

Base no art. 33 da LGPD: cláusulas contratuais com o subprocessador e, quando aplicável, o consentimento ou a execução de contrato do controlador. A ANPD regulamentou as cláusulas-padrão pela Resolução CD/ANPD nº 19/2024; o jurídico confere a aderência dos DPAs dos subprocessadores.
