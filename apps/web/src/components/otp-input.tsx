"use client";

import { useRef } from "react";
import { applyOtpInput } from "@/lib/auth/otp";

interface Props {
  digits: readonly string[];
  onChange: (digits: string[]) => void;
}

export function OtpInput({ digits, onChange }: Props) {
  const inputs = useRef<(HTMLInputElement | null)[]>([]);

  function update(index: number, value: string) {
    const result = applyOtpInput(digits, index, value);
    onChange(result.digits);
    inputs.current[result.focus]?.focus();
  }

  return (
    <div className="otp">
      {digits.map((digit, index) => (
        <input
          key={index}
          ref={(element) => {
            inputs.current[index] = element;
          }}
          aria-label={`Dígito ${String(index + 1)}`}
          inputMode="numeric"
          autoComplete={index === 0 ? "one-time-code" : "off"}
          autoFocus={index === 0}
          value={digit}
          onChange={(event) => {
            update(index, event.target.value.slice(digit.length ? 1 : 0) || event.target.value);
          }}
          onKeyDown={(event) => {
            if (event.key === "Backspace" && digit === "" && index > 0) {
              inputs.current[index - 1]?.focus();
            }
          }}
        />
      ))}
    </div>
  );
}
