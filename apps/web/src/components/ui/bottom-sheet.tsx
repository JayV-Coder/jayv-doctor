"use client";

import { useRef, type ReactNode } from "react";

// `<dialog>` nativo: foco preso, Esc fecha e o resto da página fica inerte, sem biblioteca.
export function BottomSheet({
  title,
  trigger,
  triggerLabel,
  triggerClassName = "btn",
  onClose,
  children,
}: {
  title: string;
  trigger: ReactNode;
  triggerLabel?: string;
  triggerClassName?: string;
  // Ao fechar, por botão, Esc ou toque no fundo: limpa erros para a próxima abertura.
  onClose?: () => void;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLParagraphElement>(null);

  // O foco vai para o título, não para o primeiro campo: senão o teclado virtual cobre a folha.
  function open() {
    dialog.current?.showModal();
    heading.current?.focus();
  }

  return (
    <>
      <button
        type="button"
        className={triggerClassName}
        aria-label={triggerLabel}
        aria-haspopup="dialog"
        onClick={open}
      >
        {trigger}
      </button>
      <dialog
        ref={dialog}
        className="sheet"
        aria-label={title}
        onClose={onClose}
        onClick={(event) => {
          // Toque no fundo escurecido fecha, como nos apps nativos.
          if (event.target === event.currentTarget) event.currentTarget.close();
        }}
      >
        <div className="stack">
          <p ref={heading} className="title" tabIndex={-1}>
            {title}
          </p>
          {children}
          <button type="button" className="btn" onClick={() => dialog.current?.close()}>
            Fechar
          </button>
        </div>
      </dialog>
    </>
  );
}
