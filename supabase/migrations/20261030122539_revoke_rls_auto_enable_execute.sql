-- O Supabase cria public.rls_auto_enable() (event trigger que liga RLS em tabelas novas) com
-- EXECUTE para anon/authenticated, exposta em /rest/v1/rpc. Event triggers não checam EXECUTE
-- ao disparar, então revogar não muda o comportamento. Condicional: não existe na stack local.
do $$
begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
  end if;
end;
$$;
