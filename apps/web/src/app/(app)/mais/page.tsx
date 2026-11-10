import { cookies } from "next/headers";
import Link from "next/link";
import { SessionFooter } from "@/components/shell/session-footer";
import { ThemeSelect } from "@/components/shell/theme-select";
import { ListItem } from "@/components/ui/list-item";
import { getMe } from "@/lib/api";
import { getPrivacy } from "@/lib/privacy/api";
import { isManager } from "@/lib/orgs/labels";
import { parseTheme, THEME_COOKIE } from "@/lib/shell/theme";
import { PrivacySection } from "./privacy-section";

export const metadata = { title: "Mais · Integration AI Doctor" };

export default async function MorePage() {
  const [me, store, privacy] = await Promise.all([getMe(), cookies(), getPrivacy()]);
  const active = me?.organizations.find(({ id }) => id === me.active_tenant_id);
  const role = active?.role;

  return (
    <>
      <ul className="list">
        <ListItem href="/integracoes" title="Integrações" />
        <ListItem href="/conhecimento" title="Base de conhecimento" />
        <ListItem href="/uso" title="Uso e cotas" />
        <ListItem href="/alertas" title="Alertas" />
        <ListItem href="/chamados" title="Chamados (ITSM)" />
        {isManager(role) && <ListItem href="/membros" title="Membros e convites" />}
        {isManager(role) && <ListItem href="/auditoria" title="Auditoria" />}
        {isManager(role) && <ListItem href="/webhooks" title="Webhooks" />}
      </ul>
      {privacy && active && (
        <PrivacySection
          settings={privacy}
          manager={isManager(role)}
          owner={role === "owner"}
          slug={active.slug}
        />
      )}
      <ThemeSelect initial={parseTheme(store.get(THEME_COOKIE)?.value)} />
      <h2 className="label">Conta</h2>
      <SessionFooter />
      <p className="foot">
        <Link href="/privacidade">Política de privacidade</Link>
      </p>
    </>
  );
}
