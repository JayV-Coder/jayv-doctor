"use client";

import { useState } from "react";
import { themeCookie, type Theme } from "@/lib/shell/theme";

const OPTIONS: { value: Theme; label: string }[] = [
  { value: "system", label: "Sistema" },
  { value: "light", label: "Claro" },
  { value: "dark", label: "Escuro" },
];

export function ThemeSelect({ initial }: { initial: Theme }) {
  const [theme, setTheme] = useState(initial);

  function choose(next: Theme) {
    setTheme(next);
    document.cookie = themeCookie(next);
    const root = document.documentElement;
    if (next === "system") delete root.dataset.theme;
    else root.dataset.theme = next;
  }

  return (
    <fieldset className="choice">
      <legend className="label">Tema</legend>
      <div className="segmented">
        {OPTIONS.map(({ value, label }) => (
          <label key={value}>
            <input
              type="radio"
              name="tema"
              value={value}
              checked={theme === value}
              onChange={() => {
                choose(value);
              }}
            />
            {label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
