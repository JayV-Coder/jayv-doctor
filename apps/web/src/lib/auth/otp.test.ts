import { describe, expect, it } from "vitest";
import { applyOtpInput, EMPTY_OTP } from "./otp";

describe("applyOtpInput", () => {
  it("preenche o dígito e avança", () => {
    expect(applyOtpInput(EMPTY_OTP, 0, "4")).toEqual({
      digits: ["4", "", "", "", "", ""],
      focus: 1,
    });
  });

  it("distribui um código colado a partir da casa atual", () => {
    expect(applyOtpInput(EMPTY_OTP, 0, "481 920").digits.join("")).toBe("481920");
  });

  it("ignora o que não é dígito", () => {
    expect(applyOtpInput(EMPTY_OTP, 2, "a")).toEqual({ digits: EMPTY_OTP, focus: 2 });
  });

  it("não passa da última casa", () => {
    const { digits, focus } = applyOtpInput(EMPTY_OTP, 5, "123");
    expect(digits).toEqual(["", "", "", "", "", "1"]);
    expect(focus).toBe(5);
  });

  it("apagar limpa só a casa atual", () => {
    const filled = applyOtpInput(EMPTY_OTP, 0, "123456").digits;
    expect(applyOtpInput(filled, 3, "").digits.join("")).toBe("12356");
  });
});
