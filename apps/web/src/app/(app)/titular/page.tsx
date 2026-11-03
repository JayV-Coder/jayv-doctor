import { SubjectForm } from "./subject-form";

export const metadata = { title: "Direitos do titular · Integration AI Doctor" };

// A pedido do controlador (LGPD): Owner ou Admin com MFA localiza e apaga os Eventos de um
// titular pela Referência de negócio, que vira HMAC com a chave da Organização.
export default function SubjectPage() {
  return (
    <>
      <p className="small">
        Use quando o controlador pedir a exclusão dos dados de uma pessoa. A busca usa a Referência
        de negócio (como o nº do pedido) sem gravá-la: só a quantidade apagada fica na auditoria.
      </p>
      <SubjectForm />
    </>
  );
}
