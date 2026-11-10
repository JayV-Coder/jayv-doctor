import { CopyCommand } from "../conectores/novo/copy-command";

// O segredo aparece uma vez: quem recebe guarda para conferir o `X-AID-Signature`.
export function SecretOnce({ secret }: { secret: string }) {
  return (
    <div className="stack" role="status">
      <p className="alert notice">
        Guarde o segredo agora: ele não aparece de novo. Use-o para conferir a assinatura de cada
        entrega (docs/api/webhooks.md).
      </p>
      <CopyCommand command={secret} />
    </div>
  );
}
