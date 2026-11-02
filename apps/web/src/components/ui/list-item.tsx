import Link from "next/link";
import type { ReactNode } from "react";

// Vai dentro de `<ul className="list">`. Com `href`, a linha inteira é o alvo do toque.
export function ListItem({
  title,
  detail,
  href,
  trailing,
}: {
  title: ReactNode;
  detail?: ReactNode;
  href?: string;
  trailing?: ReactNode;
}) {
  const body = (
    <>
      <span className="li-text">
        <span>{title}</span>
        {detail && <span className="small">{detail}</span>}
      </span>
      {trailing}
      {href && <span aria-hidden="true">›</span>}
    </>
  );
  return (
    <li>
      {href ? (
        <Link className="li" href={href}>
          {body}
        </Link>
      ) : (
        <div className="li">{body}</div>
      )}
    </li>
  );
}
