"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { pendingInvitation } from "@/lib/orgs/pending-invitation";

const subscribe = () => () => undefined;

export function PendingInvitationNotice() {
  const pending = useSyncExternalStore(
    subscribe,
    () => pendingInvitation() !== null,
    () => false,
  );
  if (!pending) return null;
  return (
    <Link className="btn primary" href="/convites/aceitar">
      Ver convite pendente
    </Link>
  );
}
