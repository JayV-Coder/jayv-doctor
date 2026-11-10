// Formulário do Mapa de identificadores (#40): linhas por sistema viram `keys` da API.

export type Transform = { op: string; value?: string };
export type Key = { system: string; field: string; transforms?: Transform[] };
export type Lookup = {
  connector_id: string;
  entity: string;
  field: string;
  status_field: string | null;
  pad_left: number;
};

export const ROWS = 3;
export const SYSTEMS = [
  { value: "salesforce", label: "Salesforce" },
  { value: "gcp", label: "Google Cloud" },
  { value: "sap", label: "SAP" },
  { value: "mulesoft", label: "MuleSoft" },
  { value: "aws", label: "AWS" },
  { value: "azure", label: "Azure" },
  { value: "custom", label: "Outro" },
];

function text(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
}

export function keysFromForm(form: FormData): Key[] {
  const keys: Key[] = [];
  for (let row = 0; row < ROWS; row += 1) {
    const field = text(form, `field-${String(row)}`);
    if (!field) continue;
    const transforms: Transform[] = [{ op: "trim" }];
    const prefix = text(form, `prefix-${String(row)}`);
    if (prefix) transforms.push({ op: "strip_prefix", value: prefix });
    if (form.get(`zeros-${String(row)}`) === "on") transforms.push({ op: "strip_leading_zeros" });
    if (form.get(`upper-${String(row)}`) === "on") transforms.push({ op: "upper" });
    keys.push({ system: text(form, `system-${String(row)}`), field, transforms });
  }
  return keys;
}

export function lookupFromForm(form: FormData): Lookup | null {
  const connector = text(form, "connector");
  if (!connector) return null;
  return {
    connector_id: connector,
    entity: text(form, "entity"),
    field: text(form, "lookup-field"),
    status_field: text(form, "status-field") || null,
    pad_left: Number(text(form, "pad") || "0"),
  };
}

const OPS: Record<string, (value?: string) => string> = {
  strip_prefix: (value) => `sem o prefixo ${value ?? ""}`,
  strip_suffix: (value) => `sem o sufixo ${value ?? ""}`,
  strip_leading_zeros: () => "sem zeros à esquerda",
  upper: () => "maiúsculas",
  lower: () => "minúsculas",
};

export function keySummary(key: Key): string {
  const system = SYSTEMS.find((item) => item.value === key.system)?.label ?? key.system;
  const steps = (key.transforms ?? [])
    .map((step) => OPS[step.op]?.(step.value))
    .filter((step): step is string => Boolean(step));
  return `${system} · ${key.field}${steps.length > 0 ? ` (${steps.join(", ")})` : ""}`;
}
