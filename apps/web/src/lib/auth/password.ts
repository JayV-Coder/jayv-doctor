// As regras da senha nova (as mesmas do Supabase Auth: 12 caracteres, com minúsculas,
// maiúsculas e números). O servidor confere de novo; esta cópia marca a lista enquanto a
// pessoa digita.
export const PASSWORD_MIN = 12;

export type PasswordRule = "length" | "lower" | "upper" | "digit";

export const PASSWORD_RULES: { rule: PasswordRule; label: string }[] = [
  { rule: "length", label: `Ao menos ${String(PASSWORD_MIN)} caracteres` },
  { rule: "lower", label: "Uma letra minúscula" },
  { rule: "upper", label: "Uma letra maiúscula" },
  { rule: "digit", label: "Um número" },
];

export function passwordRules(password: string): Record<PasswordRule, boolean> {
  return {
    // Por caractere (pontos de código), não por unidade UTF-16: emoji conta como um.
    length: Array.from(password).length >= PASSWORD_MIN,
    lower: /\p{Ll}/u.test(password),
    upper: /\p{Lu}/u.test(password),
    digit: /\p{Nd}/u.test(password),
  };
}

export function passwordOk(password: string): boolean {
  return Object.values(passwordRules(password)).every(Boolean);
}
