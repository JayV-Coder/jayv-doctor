import { notFound } from "next/navigation";
import { connection } from "next/server";
import {
  DiagnosisCard,
  DiagnosisEvidence,
  DiagnosisHypotheses,
  DiagnosisRecommendations,
} from "@/components/diagnosis/diagnosis-card";
import type { DiagnosisDetail } from "@/lib/diagnoses/api";

export const metadata = {
  title: "Estados do Diagnóstico · Integration AI Doctor",
  robots: "noindex",
};

const BASE: DiagnosisDetail = {
  id: "00000000-0000-4000-8000-000000000d01",
  incident_id: "00000000-0000-4000-8000-000000000501",
  version: 1,
  status: "published",
  stage: "done",
  requested_mode: "hybrid",
  mode: "hybrid",
  classification: "UPSTREAM_TIMEOUT",
  confidence: 0.68,
  requires_human_review: true,
  created_at: "2026-11-02T14:21:00Z",
  published_at: "2026-11-02T14:21:20Z",
  probable_cause: "Tempo limite excedido na chamada ao SAP (gateway 30 s).",
  responsible_system: null,
  include_knowledge_base: true,
  verification_notes: ["Evidência descartada: 'evt-999' não pertence ao Incidente."],
  provider: "anthropic",
  model: "claude-sonnet-5-5",
  ruleset_version: "2026.10.1",
  input_tokens: 1200,
  output_tokens: 300,
  duration_ms: 20000,
  error: null,
  hypotheses: [
    { rank: 1, statement: "Timeout no SAP ao processar BAPI_SALESORDER_CREATE", confidence: 0.6 },
    { rank: 2, statement: "Saturação do serviço intermediário", confidence: 0.3 },
  ],
  evidence: [
    {
      rank: 1,
      kind: "rule_match",
      ref_id: "00000000-0000-4000-8000-000000000601",
      event_timestamp: null,
      label: "INT-003 · Tempo esgotado",
      finding: "Gateway retornou HTTP 504",
      event_id: "00000000-0000-4000-8000-000000000701",
      execution_id: "00000000-0000-4000-8000-000000000401",
    },
    {
      rank: 2,
      kind: "event",
      ref_id: "00000000-0000-4000-8000-000000000702",
      event_timestamp: "2026-11-02T14:02:31Z",
      label: "BAPI_SALESORDER_CREATE · ERROR",
      finding: "Duração atingiu 30.000 ms",
      event_id: "00000000-0000-4000-8000-000000000702",
      execution_id: "00000000-0000-4000-8000-000000000401",
    },
  ],
  recommendations: [
    { rank: 1, text: "Consultar o processamento correspondente no SAP", kind: "investigate" },
    { rank: 2, text: "Confirmar a existência do pedido antes de reenviar", kind: "verify" },
  ],
};

const STATES: { name: string; diagnosis: DiagnosisDetail }[] = [
  { name: "queued", diagnosis: { ...BASE, status: "queued", stage: "queued", confidence: null } },
  { name: "running", diagnosis: { ...BASE, status: "running", stage: "llm", confidence: null } },
  { name: "published", diagnosis: BASE },
  {
    name: "inconclusive",
    diagnosis: { ...BASE, status: "inconclusive", evidence: [], recommendations: [] },
  },
  {
    name: "failed_llm",
    diagnosis: { ...BASE, status: "failed_llm", mode: "rules_only", confidence: 0.5, model: null },
  },
  {
    name: "failed",
    diagnosis: { ...BASE, status: "failed", error: "Incidente não encontrado.", confidence: null },
  },
];

// Estados do card de Diagnóstico para os testes de componente do E2E. Fora deles, não existe.
export default async function DiagnosisStatesPage() {
  await connection();
  if (process.env.COMPONENT_CATALOG !== "1") notFound();
  return (
    <main className="content">
      <h1>Estados do Diagnóstico</h1>
      {STATES.map(({ name, diagnosis }) => (
        <article key={name} aria-label={`Estado ${name}`} className="stack">
          <h2 className="label">{name}</h2>
          <DiagnosisCard diagnosis={diagnosis} />
          <DiagnosisHypotheses diagnosis={diagnosis} />
          <DiagnosisRecommendations diagnosis={diagnosis} />
          <DiagnosisEvidence diagnosis={diagnosis} />
        </article>
      ))}
    </main>
  );
}
