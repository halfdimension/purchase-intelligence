-- Phase 1, Milestone 3A
-- Supabase Auth -> automatic application profile creation.
--
-- Current pre-migration state was verified as:
--
--   auth.users      = 0
--   public.profiles = 0
--
-- Therefore no historical user backfill is required.
--
-- This migration does NOT:
--
--   - modify Phase 0 tables
--   - create RLS policies yet
--   - change frontend authentication yet
--   - switch crawler/runtime behavior
--
-- It only establishes:
--
-- auth.users INSERT
--        ↓
-- public.profiles INSERT


-- ============================================================
-- New Auth User Handler
--
-- Supabase Auth remains the owner of authentication identity.
--
-- This function creates the corresponding application profile.
--
-- SECURITY DEFINER is required because the Auth trigger writes
-- into public.profiles even though that table has RLS enabled.
--
-- An empty search_path avoids unsafe object resolution inside
-- this privileged function.
-- ============================================================

create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    insert into public.profiles (
        id,
        email,
        display_name,
        role
    )
    values (
        new.id,
        new.email,
        new.raw_user_meta_data ->> 'display_name',
        'user'
    );

    return new;
end;
$$;


-- Prevent normal application users from directly invoking this
-- privileged function.
revoke execute
on function public.handle_new_auth_user()
from public, anon, authenticated;


-- ============================================================
-- Auth User Insert Trigger
-- ============================================================

drop trigger if exists trg_auth_user_created
    on auth.users;


create trigger trg_auth_user_created
after insert on auth.users
for each row
execute function public.handle_new_auth_user();

