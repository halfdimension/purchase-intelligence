-- Phase 1, Milestone 3E
-- Notification, preference and feature-entitlement security.
--
-- User-owned mutable data:
--
--   notification_preferences
--
-- User-visible but backend-owned data:
--
--   notifications
--   notification_deliveries
--
-- Shared read-only configuration:
--
--   feature_flags
--
-- User-visible but privileged/backend-managed configuration:
--
--   user_feature_entitlements
--
-- Normal authenticated users must never be able to manufacture:
--
--   notifications
--   delivery results
--   feature grants


-- ============================================================
-- NOTIFICATION PREFERENCES — PRIVILEGES
-- ============================================================

revoke all
on table public.notification_preferences
from public, anon, authenticated;


grant select
on table public.notification_preferences
to authenticated;


-- user_id is supplied on initial creation and must equal auth.uid().
--
-- timestamps are database-managed.

grant insert (
    user_id,
    email_enabled,
    email_address,
    push_enabled,
    telegram_enabled,
    whatsapp_enabled
)
on table public.notification_preferences
to authenticated;


-- Users may change preference values, but cannot change ownership
-- or timestamps.

grant update (
    email_enabled,
    email_address,
    push_enabled,
    telegram_enabled,
    whatsapp_enabled
)
on table public.notification_preferences
to authenticated;


-- No DELETE privilege is granted.
--
-- Preferences can be disabled/reset instead.
-- Account deletion cascades through profiles.


-- ============================================================
-- NOTIFICATION PREFERENCES — SELECT
-- ============================================================

drop policy if exists notification_preferences_select_own
on public.notification_preferences;


create policy notification_preferences_select_own
on public.notification_preferences
for select
to authenticated
using (
    user_id = (select auth.uid())
);


-- ============================================================
-- NOTIFICATION PREFERENCES — INSERT
-- ============================================================

drop policy if exists notification_preferences_insert_own
on public.notification_preferences;


create policy notification_preferences_insert_own
on public.notification_preferences
for insert
to authenticated
with check (
    user_id = (select auth.uid())

    and (
        push_enabled = false

        or exists (
            select 1
            from public.feature_flags feature
            where feature.key = 'push_notifications'
              and feature.default_enabled = true
        )

        or exists (
            select 1
            from public.user_feature_entitlements entitlement
            where entitlement.user_id = (select auth.uid())
              and entitlement.feature_key = 'push_notifications'
              and entitlement.enabled = true
        )
    )

    and (
        telegram_enabled = false

        or exists (
            select 1
            from public.feature_flags feature
            where feature.key = 'telegram_notifications'
              and feature.default_enabled = true
        )

        or exists (
            select 1
            from public.user_feature_entitlements entitlement
            where entitlement.user_id = (select auth.uid())
              and entitlement.feature_key = 'telegram_notifications'
              and entitlement.enabled = true
        )
    )

    and (
        whatsapp_enabled = false

        or exists (
            select 1
            from public.feature_flags feature
            where feature.key = 'whatsapp_notifications'
              and feature.default_enabled = true
        )

        or exists (
            select 1
            from public.user_feature_entitlements entitlement
            where entitlement.user_id = (select auth.uid())
              and entitlement.feature_key = 'whatsapp_notifications'
              and entitlement.enabled = true
        )
    )
);


-- ============================================================
-- NOTIFICATION PREFERENCES — UPDATE
-- ============================================================

drop policy if exists notification_preferences_update_own
on public.notification_preferences;


create policy notification_preferences_update_own
on public.notification_preferences
for update
to authenticated
using (
    user_id = (select auth.uid())
)
with check (
    user_id = (select auth.uid())

    and (
        push_enabled = false

        or exists (
            select 1
            from public.feature_flags feature
            where feature.key = 'push_notifications'
              and feature.default_enabled = true
        )

        or exists (
            select 1
            from public.user_feature_entitlements entitlement
            where entitlement.user_id = (select auth.uid())
              and entitlement.feature_key = 'push_notifications'
              and entitlement.enabled = true
        )
    )

    and (
        telegram_enabled = false

        or exists (
            select 1
            from public.feature_flags feature
            where feature.key = 'telegram_notifications'
              and feature.default_enabled = true
        )

        or exists (
            select 1
            from public.user_feature_entitlements entitlement
            where entitlement.user_id = (select auth.uid())
              and entitlement.feature_key = 'telegram_notifications'
              and entitlement.enabled = true
        )
    )

    and (
        whatsapp_enabled = false

        or exists (
            select 1
            from public.feature_flags feature
            where feature.key = 'whatsapp_notifications'
              and feature.default_enabled = true
        )

        or exists (
            select 1
            from public.user_feature_entitlements entitlement
            where entitlement.user_id = (select auth.uid())
              and entitlement.feature_key = 'whatsapp_notifications'
              and entitlement.enabled = true
        )
    )
);


-- ============================================================
-- NOTIFICATIONS — PRIVILEGES
--
-- Notifications are generated by trusted backend/evaluator code.
--
-- Normal users may read their own notification history but may
-- not insert, update or delete notification records.
-- ============================================================

revoke all
on table public.notifications
from public, anon, authenticated;


grant select
on table public.notifications
to authenticated;


-- ============================================================
-- NOTIFICATIONS — SELECT
--
-- Direct ownership is user_id.
--
-- If the notification still references a watch, that watch must
-- also belong to the same authenticated user.
--
-- watch_id becomes NULL automatically when a watch is deleted,
-- so historical notifications can remain visible afterward.
-- ============================================================

drop policy if exists notifications_select_own
on public.notifications;


create policy notifications_select_own
on public.notifications
for select
to authenticated
using (
    user_id = (select auth.uid())

    and (
        watch_id is null

        or exists (
            select 1
            from public.watch_intents watch
            where watch.id = notifications.watch_id
              and watch.user_id = (select auth.uid())
        )
    )
);


-- ============================================================
-- NOTIFICATION DELIVERIES — PRIVILEGES
--
-- Provider state is backend-owned.
--
-- Normal users may inspect delivery status for their own
-- notifications but cannot create or alter provider state.
-- ============================================================

revoke all
on table public.notification_deliveries
from public, anon, authenticated;


grant select
on table public.notification_deliveries
to authenticated;


-- ============================================================
-- NOTIFICATION DELIVERIES — SELECT
--
-- Ownership is inherited through notification_id.
-- ============================================================

drop policy if exists notification_deliveries_select_own
on public.notification_deliveries;


create policy notification_deliveries_select_own
on public.notification_deliveries
for select
to authenticated
using (
    exists (
        select 1
        from public.notifications notification
        where notification.id =
            notification_deliveries.notification_id
          and notification.user_id = (select auth.uid())
    )
);


-- ============================================================
-- FEATURE FLAGS — PRIVILEGES
--
-- Feature definitions are shared configuration.
--
-- Authenticated users may inspect definitions so the application
-- can understand available capabilities.
--
-- Normal clients may not change feature definitions.
-- ============================================================

revoke all
on table public.feature_flags
from public, anon, authenticated;


grant select
on table public.feature_flags
to authenticated;


-- ============================================================
-- FEATURE FLAGS — SELECT
-- ============================================================

drop policy if exists feature_flags_authenticated_read
on public.feature_flags;


create policy feature_flags_authenticated_read
on public.feature_flags
for select
to authenticated
using (
    true
);


-- ============================================================
-- USER FEATURE ENTITLEMENTS — PRIVILEGES
--
-- Users may inspect their own feature grants.
--
-- They MUST NOT be able to grant, revoke or modify their own
-- entitlements.
--
-- Entitlement writes remain privileged backend/admin operations.
-- ============================================================

revoke all
on table public.user_feature_entitlements
from public, anon, authenticated;


grant select
on table public.user_feature_entitlements
to authenticated;


-- ============================================================
-- USER FEATURE ENTITLEMENTS — SELECT
-- ============================================================

drop policy if exists user_feature_entitlements_select_own
on public.user_feature_entitlements;


create policy user_feature_entitlements_select_own
on public.user_feature_entitlements
for select
to authenticated
using (
    user_id = (select auth.uid())
);

