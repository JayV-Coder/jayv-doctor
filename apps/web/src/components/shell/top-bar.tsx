"use client";

import { usePathname } from "next/navigation";
import { OrgSwitcher } from "@/components/org-switcher";
import type { Organization } from "@/lib/api";
import { pageTitle } from "@/lib/shell/nav";

export function TopBar({
  organizations,
  active,
}: {
  organizations: Organization[];
  active: Organization;
}) {
  return (
    <header className="top">
      <h1>{pageTitle(usePathname())}</h1>
      <OrgSwitcher organizations={organizations} active={active} />
    </header>
  );
}
