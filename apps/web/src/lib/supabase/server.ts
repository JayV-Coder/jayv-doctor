import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { SUPABASE_KEY, SUPABASE_URL } from "./env";

export async function createClient() {
  const store = await cookies();
  return createServerClient(SUPABASE_URL, SUPABASE_KEY, {
    cookies: {
      getAll: () => store.getAll(),
      setAll(toSet) {
        // Em Server Component os cookies são só leitura; quem renova a sessão é o proxy.
        try {
          for (const { name, value, options } of toSet) store.set(name, value, options);
        } catch {
          return;
        }
      },
    },
  });
}
