import type { RegistrationToken } from "@/lib/api";
import { CopyCommand } from "../novo/copy-command";

// O token aparece uma vez: vale 24 h e para um registro só.
export function InstallCommand({ token }: { token: RegistrationToken }) {
  return (
    <div className="stack" role="status">
      <p className="alert notice">
        Rode o comando na máquina do agente, na rede do SAP. O token vale {token.expires_in_hours} h
        e não aparece de novo.
      </p>
      <CopyCommand command={token.install_command} />
      <p className="muted small">
        O agente só abre conexões de saída (HTTPS na porta 443). Nenhuma porta de entrada precisa
        ser liberada.
      </p>
    </div>
  );
}
