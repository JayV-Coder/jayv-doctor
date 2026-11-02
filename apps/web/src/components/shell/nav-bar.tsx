"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { activeTab, TABS } from "@/lib/shell/nav";
import { NavIcon } from "./nav-icon";

// Uma navegação só: barra inferior no celular e lateral a partir de 768 px, pelo CSS.
export function NavBar() {
  const current = activeTab(usePathname());

  return (
    <nav className="nav" aria-label="Navegação principal">
      <p className="nav-brand">
        <span className="logo-mark" aria-hidden="true">
          ❯
        </span>{" "}
        Integration AI Doctor
      </p>
      {TABS.map(({ href, label, icon }) => (
        <Link key={href} href={href} aria-current={href === current ? "page" : undefined}>
          <NavIcon name={icon} />
          {label}
        </Link>
      ))}
    </nav>
  );
}
