"use client";

// Tenta de novo a própria página: um link para "/" tiraria a pessoa de onde ela estava.
export function ReloadButton({ children = "Tentar de novo" }: { children?: string }) {
  return (
    <button
      type="button"
      className="btn"
      onClick={() => {
        window.location.reload();
      }}
    >
      {children}
    </button>
  );
}
