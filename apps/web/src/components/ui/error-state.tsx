import type { ReactNode } from "react";

export function ErrorState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="empty error-state" role="alert">
      <h2 className="title">{title}</h2>
      <p className="muted small">{children}</p>
      {action}
    </section>
  );
}
