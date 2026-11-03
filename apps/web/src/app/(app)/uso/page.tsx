import type { ApiComponents } from "@aid/contracts";
import { Chip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { apiFetch } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { amountText, quotaWarning, resourceLabel } from "@/lib/usage/labels";

export const metadata = { title: "Uso e cotas · Integration AI Doctor" };

type Usage = ApiComponents["schemas"]["Usage"];

const PLANS: Record<string, string> = {
  pilot: "Piloto",
  professional: "Profissional",
  enterprise: "Enterprise",
};

// Tela 17: barras por recurso, aviso de Cota e o consumo de IA do mês.
export default async function UsagePage() {
  const response = await apiFetch("/usage").catch(() => null);
  const usage = response?.ok ? ((await response.json()) as Usage) : null;
  if (!usage) {
    return (
      <ErrorState title="Não foi possível carregar o uso" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  const tokens = usage.llm.input_tokens + usage.llm.output_tokens;
  return (
    <>
      <div className="row-between">
        <p className="small">Consumo da Organização neste mês e os limites do plano.</p>
        <Chip tone="info">{PLANS[usage.plan] ?? usage.plan}</Chip>
      </div>
      <ul className="list" aria-label="Uso por recurso">
        {usage.resources.map((item) => {
          const warning = quotaWarning(item.resource, item.ratio);
          const percent = Math.min(100, Math.round(item.ratio * 100));
          return (
            <li key={item.resource}>
              <div className="li usage">
                <span className="li-text">
                  <span className="row-between">
                    <span>{resourceLabel(item.resource)}</span>
                    <span className="small">
                      {amountText(item.resource, item.used)}/{amountText(item.resource, item.quota)}
                    </span>
                  </span>
                  <span
                    className="confidence-track"
                    role="meter"
                    aria-label={`Uso de ${resourceLabel(item.resource)}`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={percent}
                  >
                    <i
                      data-tone={
                        item.ratio >= 1 ? "danger" : item.ratio >= 0.8 ? "warning" : undefined
                      }
                      style={{ width: `${String(percent)}%` }}
                    />
                  </span>
                  {warning && (
                    <span className="small usage-warning" role="status">
                      ⚠ {warning}
                    </span>
                  )}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="note">
        IA no mês: {formatNumber(tokens)} tokens
        {usage.llm.cost_estimate !== null
          ? ` · custo estimado US$ ${usage.llm.cost_estimate.toFixed(2)}`
          : " · custo estimado indisponível (tabela de preços não configurada)"}
        .
      </p>
    </>
  );
}
