import { cookies } from "next/headers";
import Link from "next/link";
import { SessionFooter } from "@/components/shell/session-footer";
import { ThemeSelect } from "@/components/shell/theme-select";
import { ListItem } from "@/components/ui/list-item";
import { getMe } from "@/lib/api";
import { isManager } from "@/lib/orgs/labels";
import { parseTheme, THEME_COOKIE } from "@/lib/shell/theme";

export const metadata = { title: "Mais · Integration AI Doctor" };

export default async function MorePage() {
  const [me, store] = await Promise.all([getMe(), cookies()]);
  const role = me?.organizations.find(({ id }) => id === me.active_tenant_id)?.role;

  return (
    <>
      <ul className="list">
        <ListItem href="/integracoes" title="Integrações" />
        {isManager(role) && <ListItem href="/membros" title="Membros e convites" />}
      </ul>
      <ThemeSelect initial={parseTheme(store.get(THEME_COOKIE)?.value)} />
      <h2 className="label">Conta</h2>
      <SessionFooter />
      <p className="foot">
        <Link href="/privacidade">Política de privacidade</Link>
      </p>
    </>
  );
}
