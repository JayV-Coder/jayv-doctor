// Rascunho do assistente do GCP (Tela 12). Fica no sessionStorage para quem sai e volta não
// perder o progresso, e nunca leva a credencial: ela só existe na memória da página.

export const DRAFT_KEY = "aid:conector-gcp";
export const SEVERITIES = ["DEFAULT", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL"] as const;

export interface Draft {
  step: 1 | 2 | 3 | 4;
  name: string;
  project_id: string;
  services: string;
  min_severity: (typeof SEVERITIES)[number];
  filter: string;
  sync_interval_seconds: number;
  backfill_hours: 24 | 168;
  integration_id: string;
}

export const EMPTY_DRAFT: Draft = {
  step: 1,
  name: "",
  project_id: "",
  services: "",
  min_severity: "DEFAULT",
  filter: "",
  sync_interval_seconds: 300,
  backfill_hours: 24,
  integration_id: "",
};

// Mesma regra do conector (packages/connectors/.../gcp/connector.py).
const PROJECT = /^[a-z][a-z0-9-]{4,28}[a-z0-9]$/;

export function validProject(value: string): boolean {
  return PROJECT.test(value);
}

export function buildConfig(draft: Draft): Record<string, unknown> {
  const services = draft.services
    .split(",")
    .map((service) => service.trim())
    .filter(Boolean);
  const filter = draft.filter.trim();
  return {
    project_id: draft.project_id,
    auth: "key",
    ...(services.length > 0 && { services }),
    ...(draft.min_severity !== "DEFAULT" && { min_severity: draft.min_severity }),
    ...(filter && { filter }),
    backfill_hours: draft.backfill_hours,
  };
}

// Só os campos conhecidos, com os tipos certos; qualquer outra coisa volta ao começo.
export function readDraft(raw: string | null): Draft {
  if (!raw) return EMPTY_DRAFT;
  try {
    const saved = JSON.parse(raw) as Partial<Record<keyof Draft, unknown>>;
    const draft: Draft = { ...EMPTY_DRAFT };
    for (const key of Object.keys(EMPTY_DRAFT) as (keyof Draft)[]) {
      if (typeof saved[key] !== typeof EMPTY_DRAFT[key]) return EMPTY_DRAFT;
      Object.assign(draft, { [key]: saved[key] });
    }
    const steps: unknown[] = [1, 2, 3, 4];
    const backfills: unknown[] = [24, 168];
    const severities: readonly unknown[] = SEVERITIES;
    if (
      !steps.includes(draft.step) ||
      !backfills.includes(draft.backfill_hours) ||
      !severities.includes(draft.min_severity)
    ) {
      return EMPTY_DRAFT;
    }
    return draft;
  } catch {
    return EMPTY_DRAFT;
  }
}

// Só leitura de logs: a Service Account não ganha nenhum outro papel no projeto do cliente.
export function gcloudCommands(project: string): string[] {
  const account = `doctor-reader@${project}.iam.gserviceaccount.com`;
  return [
    `gcloud iam service-accounts create doctor-reader --project=${project} --display-name="Integration AI Doctor"`,
    `gcloud projects add-iam-policy-binding ${project} --member="serviceAccount:${account}" --role="roles/logging.viewer"`,
    `gcloud iam service-accounts keys create doctor-reader.json --iam-account=${account}`,
  ];
}
