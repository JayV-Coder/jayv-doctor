import Link from "next/link";
import { notFound } from "next/navigation";
import { Chip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReloadButton } from "@/components/ui/reload-button";
import { getMe, listConnectors, listIntegrations, listMappings } from "@/lib/api";
import { keySummary, type Key } from "@/lib/correlation/form";
import { flowLabel } from "@/lib/integrations/labels";
import { canManage } from "@/lib/orgs/labels";
import { DeleteMapping } from "./delete-mapping";
import { MappingForm } from "./mapping-form";

export const metadata = { title: "Mapa entre sistemas · Integration AI Doctor" };

// Mapas de identificadores (#40): todo Papel vê; Owner e Admin com MFA cadastram e removem.
export default async function MappingsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [me, integrations, mappings, connectors] = await Promise.all([
    getMe(),
    listIntegrations(),
    listMappings(id),
    listConnectors(),
  ]);
  if (mappings === "not_found") notFound();
  const integration = integrations?.find((item) => item.id === id);
  if (mappings === null || !integration) {
    return (
      <ErrorState title="Não foi possível carregar os mapas" action={<ReloadButton />}>
        O serviço não respondeu. Tente de novo em instantes.
      </ErrorState>
    );
  }
  const manager = canManage(me);
  const lookups = (connectors ?? [])
    .filter((item) => item.provider === "salesforce" || item.provider === "odata")
    .map(({ id: connector, name, provider }) => ({ id: connector, name, provider }));

  return (
    <>
      <Link className="small" href="/integracoes">
        ‹ Integrações
      </Link>
      <div className="row-between">
        <p className="small">
          {integration.name} · {flowLabel(integration.source_system, integration.target_system)}
        </p>
        {manager && (
          <MappingForm
            integration={id}
            source={integration.source_system}
            target={integration.target_system}
            connectors={lookups}
          />
        )}
      </div>
      {mappings.length === 0 && (
        <EmptyState title="Nenhum mapa">
          {manager
            ? "Diga onde cada sistema guarda a mesma chave (o nº do pedido, por exemplo) para a Timeline juntar Salesforce, middleware e SAP numa Execução."
            : "Peça a um Owner ou Admin para mapear as chaves entre os sistemas desta Integração."}
        </EmptyState>
      )}
      {mappings.map((mapping) => (
        <article key={mapping.id} className="card" aria-labelledby={`map-${mapping.id}`}>
          <div className="row-between">
            <h2 id={`map-${mapping.id}`} className="t">
              {mapping.name}
            </h2>
            <span className="row-wrap">
              {mapping.reconcile && <Chip tone="info">divergência</Chip>}
              {mapping.lookup && <Chip tone="info">consulta</Chip>}
            </span>
          </div>
          <ul className="small">
            {(mapping.keys as Key[]).map((key, index) => (
              <li key={index}>{keySummary(key)}</li>
            ))}
          </ul>
          <dl className="kv">
            <dt>janela</dt>
            <dd>{mapping.window_minutes} min</dd>
            {mapping.lookup && (
              <>
                <dt>consulta</dt>
                <dd>
                  {String(mapping.lookup.entity)} · {String(mapping.lookup.field)}
                </dd>
              </>
            )}
          </dl>
          {manager && <DeleteMapping integration={id} id={mapping.id} name={mapping.name} />}
        </article>
      ))}
    </>
  );
}
