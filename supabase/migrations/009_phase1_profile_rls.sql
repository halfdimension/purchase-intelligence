-- Phase 1, Milestone 3B
-- Secure authenticated access to public.profiles.
--
-- Goals:
--
--   authenticated user:
--     - may read their own profile
--     - may update display_name
--     - may update avatar_url
--
--   authenticated user may NOT:
--     - change id
--     - change email
--     - change role
--     - insert profiles directly
--     - delete profiles directly
--     - access another user's profile
--
-- Profile creation remains owned by:
--
--   auth.users INSERT
--        ↓
--   public.handle_new_auth_user()
--        ↓
--   public.profiles INSERT


-- ============================================================
-- Remove broad client privileges first.
--
-- This makes the permission model explicit rather than relying
-- on whatever default grants currently exist.
-- ============================================================

revoke all
on table public.profiles
from public, anon, authenticated;


-- ============================================================
-- Authenticated users may read profile rows.
--
-- RLS below restricts the readable row to auth.uid().
-- ============================================================

grant select
on table public.profiles
to authenticated;


-- ============================================================
-- Authenticated users may update ONLY safe profile fields.
--
-- They intentionally receive no UPDATE privilege on:
--
--   id
--   email
--   role
--   created_at
--   updated_at
--
-- updated_at is still maintained internally by the existing
-- trigger.
-- ============================================================

grant update (
    display_name,
    avatar_url
)
on table public.profiles
to authenticated;


-- ============================================================
-- RLS policies
-- ============================================================

drop policy if exists profiles_select_own
on public.profiles;


create policy profiles_select_own
on public.profiles
for select
to authenticated
using (
    (select auth.uid()) = id
);


drop policy if exists profiles_update_own
on public.profiles;


create policy profiles_update_own
on public.profiles
for update
to authenticated
using (
    (select auth.uid()) = id
)
with check (
    (select auth.uid()) = id
);

