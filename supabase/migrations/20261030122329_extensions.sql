-- Extensões da plataforma (ADR-0001). pgcrypto já vem habilitada no Supabase;
-- pgtap é instalada só pelos testes (supabase/tests/helpers), nunca em produção.
create extension if not exists pgcrypto with schema extensions;
create extension if not exists vector with schema extensions;
create extension if not exists pg_cron with schema pg_catalog;

create schema if not exists partman;
create extension if not exists pg_partman with schema partman;
