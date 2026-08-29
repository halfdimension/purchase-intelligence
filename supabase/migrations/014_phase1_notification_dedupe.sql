begin;

-- ============================================================
-- Phase 1 Notification Dedupe
--
-- A dedupe_key represents one logical notification event.
--
-- The application generates the same key when retrying the
-- same false -> true watch transition. Enforcing uniqueness in
-- PostgreSQL prevents concurrent workers from creating duplicate
-- notification records for that same event.
-- ============================================================

drop index if exists public.idx_notifications_dedupe_key;

create unique index if not exists uq_notifications_dedupe_key
    on public.notifications(dedupe_key)
    where dedupe_key is not null;

commit;
