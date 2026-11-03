import { getPrivacy } from "@/lib/privacy/api";
import { subprocessors } from "@/lib/privacy/labels";

export const metadata = { title: "Subprocessadores · Integration AI Doctor" };

// Quem trata os dados da Organização em nome do Doctor, com a região (PRD §8). A lista segue o
// provedor de IA escolhido; com o envio ao LLM desligado, o provedor de IA não recebe nada.
export default async function SubprocessorsPage() {
  const privacy = await getPrivacy();
  const provider = privacy?.llm_provider ?? "anthropic";
  return (
    <>
      <p className="small">
        Empresas que tratam dados desta Organização em nome do Integration AI Doctor. Logs e
        documentos chegam à IA já sanitizados.
      </p>
      <ul className="list" aria-label="Subprocessadores">
        {subprocessors(provider).map((item) => (
          <li key={item.name}>
            <div className="li">
              <span className="li-text">
                <span>{item.name}</span>
                <span className="small">{item.purpose}</span>
                <span className="small">{item.region}</span>
              </span>
            </div>
          </li>
        ))}
      </ul>
      {privacy && !privacy.llm_enabled && (
        <p className="note">O envio de evidências ao LLM está desligado nesta Organização.</p>
      )}
    </>
  );
}
