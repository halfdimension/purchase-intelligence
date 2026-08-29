begin;

-- ============================================================
-- Phase 1 Notification Delivery Dedupe
--
-- One logical notification has at most one current delivery
-- state per channel.
--
-- Examples:
--
-- notification A + email    -> one row
-- notification A + telegram -> one row
--
-- Delivery retries update the existing row instead of creating
-- duplicate channel-state rows.
-- ============================================================

create unique index if not exists uq_notification_deliveries_notification_channel
    on public.notification_deliveries(
        notification_id,
        channel
    );

commit;
