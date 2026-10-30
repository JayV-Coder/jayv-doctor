export const OTP_LENGTH = 6;
export const EMPTY_OTP: readonly string[] = Array<string>(OTP_LENGTH).fill("");

// Uma casa recebe um dígito digitado ou o código inteiro colado (ou sugerido pelo teclado).
export function applyOtpInput(
  digits: readonly string[],
  index: number,
  value: string,
): { digits: string[]; focus: number } {
  const next = [...digits];
  if (value === "") {
    next[index] = "";
    return { digits: next, focus: index };
  }
  const typed = value.replace(/\D/g, "").slice(0, OTP_LENGTH - index);
  if (typed === "") return { digits: next, focus: index };
  Array.from(typed).forEach((digit, offset) => {
    next[index + offset] = digit;
  });
  return { digits: next, focus: Math.min(index + typed.length, OTP_LENGTH - 1) };
}
