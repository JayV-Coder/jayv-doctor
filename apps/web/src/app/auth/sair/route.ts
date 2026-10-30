import { NextResponse } from "next/server";
import { SITE_URL } from "@/lib/supabase/env";
import { createClient } from "@/lib/supabase/server";

export async function POST() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  return NextResponse.redirect(new URL("/login", SITE_URL), 303);
}
