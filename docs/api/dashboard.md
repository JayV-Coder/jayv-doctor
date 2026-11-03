# Dashboard

`GET /api/v1/dashboard?period=24h|7d|30d&environment=prd|hml|dev&integration_id=…` — todo Papel lê, com o RLS da Organização ativa.

| Campo | O que é |
|---|---|
| `executions` | Execuções no período (pelo primeiro Evento), com o período anterior de mesmo tamanho e a variação |
| `error_rate` | Falhas ÷ Execuções; `null` sem Execuções no período (nunca 0% inventado) |
| `mttr_minutes` | Média de `resolved_at − first_seen_at` dos Incidentes resolvidos no período. Reaberto perde o `resolved_at` e só conta de novo ao ser resolvido |
| `mttr_baseline_minutes`, `mttr_vs_baseline` | Baseline do piloto (`tenants.mttr_baseline_minutes`) e a variação contra ele |
| `open_incidents` | Incidentes `open` ou `investigating` agora |
| `failures` | Falhas por hora (24h) ou por dia (7d, 30d), em UTC |
| `failures_by_category` | Falhas pela categoria do Incidente da Execução; sem Incidente, `UNCLASSIFIED` |
| `critical_incident`, `recent_incidents` | O crítico ativo mais recente e os 5 Incidentes mais recentes |

`change` é relativa (0,12 = +12%) e vem `null` sem base de comparação.

## Agregado

Execuções e falhas saem de `doctor.execution_stats_hourly`, recalculada pelo worker de correlação (`POST /stats`, Cloud Scheduler a cada 10 min; o `pg_cron` do projeto é do jayv-coder). Cada rodada recalcula do zero as horas tocadas desde 25 min antes (Execução alterada ou que entrou num Incidente), então repetir não conta duas vezes e fusões e reaberturas se acertam. O atraso máximo fica em torno de 10 min.
