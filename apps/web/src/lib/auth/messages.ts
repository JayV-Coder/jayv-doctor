const MESSAGES: Record<string, string> = {
  invalid_credentials: "E-mail ou senha incorretos.",
  mfa_verification_failed: "Código incorreto ou expirado.",
  over_email_send_rate_limit: "Aguarde um minuto antes de pedir outro e-mail.",
  over_request_rate_limit: "Muitas tentativas. Aguarde um pouco e tente de novo.",
  weak_password: "Use ao menos 12 caracteres, com maiúsculas, minúsculas e números.",
  same_password: "A nova senha precisa ser diferente da atual.",
  reauthentication_needed: "Sua sessão é antiga. Peça um novo link de redefinição.",
};

// A mensagem do Auth vem em inglês e pode expor detalhes internos: só o `code` importa.
export function authErrorMessage(error: { code?: string | undefined }): string {
  return MESSAGES[error.code ?? ""] ?? "Não foi possível concluir. Tente de novo.";
}
