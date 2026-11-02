import type { ReactNode } from "react";

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="empty">
      <h2 className="title">{title}</h2>
      <p className="muted small">{children}</p>
      {action}
    </section>
  );
}
