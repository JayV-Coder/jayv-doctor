// Integration AI Doctor no Railway (ADR-0024), fora do GCP: a API, um serviço por worker, o
// agendador (o Cloud Scheduler daqui) e o RabbitMQ no lugar do Pub/Sub. No GCP, o deploy continua
// no Terraform (infrastructure/terraform). O app é o site da JayV (`/doctor`, ADR-0023).
//
// Aplicar: `railway config plan` e `railway config apply` (docs/operations/railway.md). Os
// segredos e as URLs ficam nas variáveis compartilhadas do projeto (`ctx.shared.*`), definidas
// uma vez no painel; este arquivo só as liga aos serviços.
import { defineRailway, github, image, service, volume, type VariableValue } from "railway/iac";

const REPO = "JayV-Coder/jayv-doctor";
const DOCKERFILE = "infrastructure/docker/python.Dockerfile";
// O que entra na imagem Python: mudança fora disso não reconstrói os serviços.
const WATCH = [
  "apps/api/**",
  "packages/**",
  "workers/**",
  "pyproject.toml",
  "uv.lock",
  DOCKERFILE,
  "!**/tests/**",
];
// O PDF do Relatório técnico (WeasyPrint): só o worker de diagnóstico gera.
const PDF_PACKAGES = "libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core";

type Env = Record<string, string | VariableValue>;

export default defineRailway((ctx, project) => {
  // Variável compartilhada do projeto (`${{shared.NOME}}`).
  const shared = (name: string): VariableValue => ctx.shared[name] as VariableValue;
  const branch = ctx.isEnvironment("production") ? "main" : (ctx.environmentName ?? "main");

  const rabbitData = volume("rabbitmq-data", { sizeMB: 1024 });
  const rabbitmq = service("rabbitmq", {
    source: image("rabbitmq:4.1-alpine"),
    volumeMounts: { "/var/lib/rabbitmq": rabbitData },
    deploy: { restartPolicyType: "ALWAYS" },
    env: {
      RABBITMQ_DEFAULT_USER: "aid",
      RABBITMQ_DEFAULT_PASS: shared("RABBITMQ_PASSWORD"),
      // O nome do nó entra no caminho dos dados: fixo, o volume serve a cada novo deploy.
      RABBITMQ_NODENAME: "rabbit@localhost",
      // Só na rede privada: nenhum domínio público nem proxy TCP.
      AMQP_URL: "amqp://aid:${{RABBITMQ_DEFAULT_PASS}}@${{RAILWAY_PRIVATE_DOMAIN}}:5672",
    },
  });

  const common = {
    LOG_LEVEL: "INFO",
    GCP_PROJECT_ID: "aid-local",
    OTEL_ENABLED: "false",
    // Escuta IPv4 e IPv6: a rede privada do Railway pode ser só IPv6.
    HOST: "::",
    PORT: "8080",
  };

  const python = (name: string, env: Env, extra: { start?: string; healthcheck?: boolean } = {}) =>
    service(name, {
      source: github(REPO, { branch }),
      build: { builder: "DOCKERFILE", dockerfilePath: DOCKERFILE, watchPatterns: WATCH },
      deploy: {
        restartPolicyType: "ALWAYS",
        ...(extra.start ? { startCommand: extra.start } : {}),
        ...(extra.healthcheck === false
          ? {}
          : { healthcheckPath: "/healthz", healthcheckTimeout: 120 }),
      },
      env: { ...common, ...env },
    });

  const worker = (name: string, env: Env = {}) =>
    python(`worker-${name}`, {
      PACKAGE: "aid-worker",
      APP: "aid_worker.main:app",
      WORKER_NAME: name,
      AMQP_URL: rabbitmq.env.AMQP_URL,
      SUPABASE_DB_URL: shared("SUPABASE_DB_URL"),
      SUPABASE_URL: shared("SUPABASE_URL"),
      ...env,
    });

  const api = python("api", {
    PACKAGE: "aid-api",
    APP: "aid_api.main:app",
    SUPABASE_DB_URL: shared("SUPABASE_DB_URL"),
    SUPABASE_URL: shared("SUPABASE_URL"),
    SUPABASE_JWT_ISSUER: "${{shared.SUPABASE_URL}}/auth/v1",
    SUPABASE_PUBLISHABLE_KEY: shared("SUPABASE_PUBLISHABLE_KEY"),
    APP_URL: shared("APP_URL"),
    AID_PUBLIC_API_URL: "https://${{RAILWAY_PUBLIC_DOMAIN}}",
    HMAC_MASTER_KEY: shared("HMAC_MASTER_KEY"),
    SMTP_URL: shared("SMTP_URL"),
    MAIL_FROM: shared("MAIL_FROM"),
    VOYAGE_API_KEY: shared("VOYAGE_API_KEY"),
    AID_VAPID_PUBLIC_KEY: shared("VAPID_PUBLIC_KEY"),
    AID_ATLASSIAN_CLIENT_ID: shared("ATLASSIAN_CLIENT_ID"),
    AID_ATLASSIAN_CLIENT_SECRET: shared("ATLASSIAN_CLIENT_SECRET"),
    AID_ATLASSIAN_REDIRECT_URI: "${{shared.APP_URL}}/doctor/tickets/jira",
    AID_AGENT_CA_KEY: shared("AGENT_CA_KEY"),
    AID_AGENT_CA_CERT: shared("AGENT_CA_CERT"),
    // Atrás do proxy de borda do Railway: um proxy só antes da API.
    AID_TRUSTED_PROXY_HOPS: "1",
    RATE_LIMIT_PER_MINUTE: "120",
  });

  const workers = [
    worker("ingestion", {
      HMAC_MASTER_KEY: shared("HMAC_MASTER_KEY"),
      SUPABASE_SERVICE_ROLE_KEY: shared("SUPABASE_SERVICE_ROLE_KEY"),
    }),
    worker("correlation"),
    worker("diagnosis", {
      SYSTEM_PACKAGES: PDF_PACKAGES,
      ANTHROPIC_API_KEY: shared("ANTHROPIC_API_KEY"),
      VOYAGE_API_KEY: shared("VOYAGE_API_KEY"),
      SUPABASE_SERVICE_ROLE_KEY: shared("SUPABASE_SERVICE_ROLE_KEY"),
      SMTP_URL: shared("SMTP_URL"),
      MAIL_FROM: shared("MAIL_FROM"),
      AID_LLM_ROUTING: shared("LLM_ROUTING"),
      AID_LLM_PRICES: shared("LLM_PRICES"),
    }),
    worker("connectors"),
    worker("notifier", {
      APP_URL: shared("APP_URL"),
      AID_PUBLIC_API_URL: "https://${{api.RAILWAY_PUBLIC_DOMAIN}}",
      SMTP_URL: shared("SMTP_URL"),
      MAIL_FROM: shared("MAIL_FROM"),
      AID_VAPID_PRIVATE_KEY: shared("VAPID_PRIVATE_KEY"),
      AID_VAPID_SUBJECT: shared("VAPID_SUBJECT"),
      AID_ATLASSIAN_CLIENT_ID: shared("ATLASSIAN_CLIENT_ID"),
      AID_ATLASSIAN_CLIENT_SECRET: shared("ATLASSIAN_CLIENT_SECRET"),
      // SSO (#48): sem os dois, a conexão SAML fica `pending_platform`.
      SUPABASE_ACCESS_TOKEN: shared("SUPABASE_ACCESS_TOKEN"),
      SUPABASE_PROJECT_REF: shared("SUPABASE_PROJECT_REF"),
    }),
    worker("relay"),
  ];

  // Os jobs do Cloud Scheduler (os mesmos do Terraform, menos métricas e backup, que são do GCP).
  const scheduler = python(
    "scheduler",
    {
      PACKAGE: "aid-worker",
      APP: "aid_worker.main:app",
      AID_WORKER_URL: "http://worker-{worker}.railway.internal:8080",
    },
    { start: "python -m aid_worker.scheduler", healthcheck: false },
  );

  return project("integration-ai-doctor", {
    resources: [rabbitData, rabbitmq, api, ...workers, scheduler],
  });
});
