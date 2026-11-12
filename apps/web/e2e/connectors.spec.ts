import { generateKeyPairSync, randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import {
  activeOrganization,
  createIntegration,
  expectNoHorizontalScroll,
  lastInvitationLink,
  ownerWithOrganization,
  PASSWORD,
  signUp,
  uniqueEmail,
} from "./helpers";

// A API do E2E aponta o conector GCP para e2e/fake-gcp.mjs (playwright.config.ts).
test.use({ viewport: { width: 390, height: 844 } });

// Chave gerada na hora: nunca uma chave real no repositório.
function serviceAccountKey(project: string): Buffer {
  const { privateKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
    privateKeyEncoding: { type: "pkcs8", format: "pem" },
    publicKeyEncoding: { type: "spki", format: "pem" },
  });
  return Buffer.from(
    JSON.stringify({
      type: "service_account",
      client_email: `doctor-reader@${project}.iam.gserviceaccount.com`,
      private_key: privateKey,
    }),
  );
}

async function uploadKey(page: Page, project: string): Promise<void> {
  await page.getByLabel("Chave JSON da Service Account").setInputFiles({
    name: "doctor-reader.json",
    mimeType: "application/json",
    buffer: serviceAccountKey(project),
  });
}

async function startWizard(page: Page, project: string): Promise<void> {
  await page.goto("/conectores");
  await page.getByRole("link", { name: "Adicionar" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Novo conector" })).toBeVisible();
  await page.getByLabel("ID do projeto").fill(project);
  await page.getByRole("button", { name: "Continuar" }).click();
  await expect(page.getByText("passo 2 de 4")).toBeVisible();
}

test("Admin configura o GCP pelo assistente, retoma o rascunho e o Analyst só vê", async ({
  page,
  context,
}) => {
  test.setTimeout(180_000);
  const organization = `Conecta ${randomUUID().slice(0, 8)}`;
  await ownerWithOrganization(page, organization);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("article", { name: "Pedidos Salesforce → SAP" })).toBeVisible();

  await page.goto("/conectores");
  await expect(page.getByText("Nenhum Conector configurado")).toBeVisible();
  await expect(page.getByRole("article", { name: "SAP Integration Suite" })).toContainText(
    "pela API",
  );
  await startWizard(page, "acme-integracoes");

  // Passo 2: comandos copiáveis com o projeto, teste com a chave.
  await expect(page.getByText(/roles\/logging\.viewer/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Continuar" })).toBeDisabled();
  await uploadKey(page, "acme-integracoes");
  await page.getByRole("button", { name: "Testar conexão" }).click();
  await expect(page.getByRole("status")).toContainText("48 registros na última hora");
  await expectNoHorizontalScroll(page);
  await page.getByRole("button", { name: "Continuar" }).click();

  // Passo 3: filtros. Quem sai e volta mantém o progresso, mas envia a chave de novo.
  await page.getByLabel("Severidade mínima").selectOption("WARNING");
  await page.getByLabel("Intervalo").selectOption({ label: "a cada 1 min" });
  await page.reload();
  await expect(page.getByText("Seu progresso foi recuperado")).toBeVisible();
  await uploadKey(page, "acme-integracoes");
  await page.getByRole("button", { name: "Testar conexão" }).click();
  await page.getByRole("button", { name: "Continuar" }).click();
  await expect(page.getByLabel("Severidade mínima")).toHaveValue("WARNING");
  await page.getByRole("button", { name: "Pré-visualizar" }).click();
  await expect(page.getByRole("region", { name: "Pré-visualização" })).toContainText(
    "48 registros na última hora atendem aos filtros",
  );
  await expectNoHorizontalScroll(page);
  await page.getByRole("button", { name: "Continuar" }).click();

  // Passo 4: vincula a Integração e ativa.
  await page.getByLabel("Integração vinculada").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Ativar conector" }).click();
  await expect(page).toHaveURL(/\/conectores\/[0-9a-f-]{36}$/);
  const detail = page.getByRole("article", { name: "gcp · acme-integracoes" });
  await expect(detail).toContainText("Pedidos Salesforce → SAP");
  await expect(detail).toContainText("a cada 1 min");
  await expect(page.getByText("Nenhuma Sincronização ainda.")).toBeVisible();

  await page.getByRole("link", { name: "‹ Conectores" }).click();
  await expect(page).toHaveURL(/\/conectores$/);
  const card = page.getByRole("article", { name: "gcp · acme-integracoes" });
  await expect(card).toContainText("ainda não sincronizou");
  await card.getByRole("button", { name: "Sincronizar" }).click();
  await expect(card.getByRole("status")).toContainText("Sincronização pedida");
  await expectNoHorizontalScroll(page);

  // O rascunho foi apagado ao ativar: o próximo assistente começa do zero.
  await page.getByRole("link", { name: "Adicionar" }).click();
  await expect(page.getByLabel("ID do projeto")).toHaveValue("");

  // Analyst (Papel padrão do convite) vê a lista, sem Adicionar, Sincronizar nem Editar.
  await page.goto("/membros");
  const analyst = uniqueEmail();
  await page.getByLabel("E-mail", { exact: true }).fill(analyst);
  await page.getByRole("button", { name: "Enviar convite" }).click();
  await expect(page.getByRole("status")).toContainText("Convite enviado");
  const link = await lastInvitationLink(analyst);
  await context.clearCookies();
  await signUp(analyst);
  await page.goto(link);
  await page.getByRole("link", { name: "Entrar para aceitar" }).click();
  await page.getByLabel("E-mail corporativo").fill(analyst);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("button", { name: "Aceitar convite" }).click();
  await expect(activeOrganization(page, organization)).toBeVisible();

  await page.goto("/conectores");
  await expect(card).toBeVisible();
  await expect(page.getByRole("link", { name: "Adicionar" })).toHaveCount(0);
  await expect(card.getByRole("button", { name: "Sincronizar" })).toHaveCount(0);
  await card.getByRole("link", { name: "Ver histórico" }).click();
  await expect(page.getByRole("button", { name: "Editar" })).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 2, name: "Sincronizações" })).toBeVisible();
});

test("teste de conexão sem permissão diz a causa e a ação", async ({ page }) => {
  await ownerWithOrganization(page, `Sem permissão ${randomUUID().slice(0, 8)}`);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("article", { name: "Pedidos Salesforce → SAP" })).toBeVisible();
  await startWizard(page, "acme-sem-permissao");

  await uploadKey(page, "acme-sem-permissao");
  await page.getByRole("button", { name: "Testar conexão" }).click();
  const alert = page.locator("p[role=alert]");
  await expect(alert).toContainText("Conceda o papel roles/logging.viewer", { ignoreCase: true });
  await expect(alert).toContainText("doctor-reader@acme-sem-permissao.iam.gserviceaccount.com");
  await expect(page.getByRole("button", { name: "Continuar" })).toBeDisabled();
});

test("Salesforce: a org sem Event Monitoring segue com as outras fontes", async ({ page }) => {
  test.setTimeout(120_000);
  await ownerWithOrganization(page, `Salesforce ${randomUUID().slice(0, 8)}`);
  await page.goto("/integracoes");
  await createIntegration(page, "Pedidos Salesforce → SAP");
  await expect(page.getByRole("article", { name: "Pedidos Salesforce → SAP" })).toBeVisible();

  await page.goto("/conectores/novo");
  await page.getByRole("link", { name: "Salesforce" }).click();
  await expect(page.getByText("Salesforce · passo 1 de 4")).toBeVisible();
  await page.getByLabel("Nome do conector").fill("Salesforce produção");
  await page.getByLabel("Objeto de log de integração (opcional)").fill("Integration_Log__c");
  await page.getByRole("button", { name: "Continuar" }).click();

  // Passo 2: JWT Bearer, sem senha; o teste diz o que a edição tem.
  const { privateKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
    privateKeyEncoding: { type: "pkcs8", format: "pem" },
    publicKeyEncoding: { type: "spki", format: "pem" },
  });
  await page.getByLabel("Consumer Key da Connected App").fill("3MVG9-conectado");
  await page.getByLabel("Usuário de integração").fill("doctor@acme.test");
  await page.getByLabel("Chave privada do certificado (PEM)").fill(privateKey);
  await page.getByRole("button", { name: "Testar conexão" }).click();
  await expect(page.getByRole("status")).toContainText("EventLogFile indisponível nesta edição");
  await expectNoHorizontalScroll(page);
  await page.getByRole("button", { name: "Continuar" }).click();

  // Passo 3: a fonte que a org não tem fica desligada; as outras já vêm marcadas.
  const sources = page.getByRole("group", { name: "Fontes" });
  await expect(sources.getByLabel("EventLogFile (Event Monitoring)")).toBeDisabled();
  await expect(sources.getByLabel("ApexLog")).toBeChecked();
  await expect(sources.getByLabel("Objeto de log de integração (__c)")).toBeChecked();
  await page.getByLabel("Campo da mensagem").fill("Message__c");
  await page.getByRole("button", { name: "Continuar" }).click();

  // Passo 4: vincula a Integração e ativa.
  await page.getByLabel("Integração vinculada").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Ativar conector" }).click();
  await expect(page).toHaveURL(/\/conectores\/[0-9a-f-]{36}$/);
  await expect(
    page.getByRole("article", { name: "salesforce · Salesforce produção" }),
  ).toBeVisible();
});
