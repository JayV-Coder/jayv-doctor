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

Execuções e falhas saem de `doctor.execution_stats_hourly` (horas em UTC). Triggers em `executions` e `incident_executions` anotam a hora antiga e a nova de toda mudança que mexe no agregado numa fila (`execution_stats_dirty`); o worker de correlação a drena (`POST /stats`, Cloud Scheduler a cada 10 min; o `pg_cron` do projeto é do jayv-coder) e recalcula cada hora do zero. Repetir não conta duas vezes; uma Execução que muda de hora sai da antiga e entra na nova; uma falha longa do job só atrasa, porque a fila espera. O atraso máximo fica em torno de 10 min. A série vem completa: intervalo sem falha aparece com zero.
