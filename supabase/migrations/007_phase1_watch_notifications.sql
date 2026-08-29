-- Phase 1, Milestone 2
-- User watch intents, notifications and feature entitlements.
--
-- This migration is additive.
--
-- It does NOT modify or remove the Phase 0 tables:
--
--   products
--   product_variants
--   price_snapshots
--   watchlists
--   watch_alert_state
--
-- It does NOT switch the current frontend, crawler or alert
-- pipeline to the new schema yet.
--
-- Depends on:
--
--   005_phase1_catalog_identity.sql
--   006_phase1_observations.sql
--
-- See:
--
--   PROJECT_CONTEXT.md
--   docs/phase-1-domain-architecture.md


-- ============================================================
-- Watch Intents
--
-- Represents what an authenticated user wants to buy/monitor.
--
-- This is intentionally different from a crawl job.
--
-- Example:
--
-- product: Nike Pegasus Premium
-- target: 18000 INR
--
-- variant_requirements:
--
-- {
--   "size": "UK 9"
-- }
--
-- conditions:
--
-- {
--   "require_in_stock": true,
--   "notify_target_price": true,
--   "notify_restock": true
-- }
--
-- A future phone watch might instead use:
--
-- {
--   "storage_gb": 256,
--   "color": "Black"
-- }
-- ============================================================

create table if not exists public.watch_intents (
    id uuid primary key default gen_random_uuid(),

    user_id uuid not null
        references public.profiles(id)
        on delete cascade,

    product_id uuid not null
        references public.canonical_products(id)
        on delete cascade,

    canonical_variant_id uuid
        references public.canonical_variants(id)
        on delete set null,

    tracking_scope text not null default 'any_listing'
        check (
            tracking_scope in (
                'specific_listing',
                'selected_listings',
                'any_listing'
            )
        ),

    target_price numeric(12, 2)
        check (
            target_price is null
            or target_price >= 0
        ),

    currency text not null default 'INR',

    variant_requirements jsonb not null
        default '{}'::jsonb,

    conditions jsonb not null
        default '{}'::jsonb,

    status text not null default 'active'
        check (
            status in (
                'active',
                'paused',
                'fulfilled',
                'archived'
            )
        ),

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);


create index if not exists idx_watch_intents_user_id
    on public.watch_intents(user_id);


create index if not exists idx_watch_intents_product_id
    on public.watch_intents(product_id);


create index if not exists idx_watch_intents_canonical_variant_id
    on public.watch_intents(canonical_variant_id);


create index if not exists idx_watch_intents_status
    on public.watch_intents(status);


create index if not exists idx_watch_intents_user_status
    on public.watch_intents(
        user_id,
        status
    );


drop trigger if exists trg_watch_intents_set_updated_at
    on public.watch_intents;


create trigger trg_watch_intents_set_updated_at
before update on public.watch_intents
for each row
execute function public.set_updated_at();


-- ============================================================
-- Watch Listing Targets
--
-- Allows a user watch to target:
--
-- specific_listing:
--     normally one row
--
-- selected_listings:
--     multiple rows
--
-- any_listing:
--     normally no rows; evaluator considers all active listings
--     for the canonical product.
--
-- Application logic must ensure selected listings belong to the
-- canonical product represented by the watch.
-- ============================================================

create table if not exists public.watch_listing_targets (
    watch_id uuid not null
        references public.watch_intents(id)
        on delete cascade,

    listing_id uuid not null
        references public.merchant_listings(id)
        on delete cascade,

    created_at timestamptz not null default now(),

    primary key (
        watch_id,
        listing_id
    )
);


create index if not exists idx_watch_listing_targets_listing_id
    on public.watch_listing_targets(listing_id);


-- ============================================================
-- Watch Evaluation State
--
-- Mutable evaluator/deduplication state.
--
-- Historical notifications are stored separately.
--
-- This is the Phase 1 replacement for the conceptual role of:
--
--   watch_alert_state
-- ============================================================

create table if not exists public.watch_evaluation_state (
    watch_id uuid primary key
        references public.watch_intents(id)
        on delete cascade,

    condition_met boolean not null default false,

    last_reason text,

    state jsonb not null
        default '{}'::jsonb,

    last_evaluated_at timestamptz not null default now(),

    last_notified_at timestamptz,

    last_notified_effective_price numeric(12, 2)
        check (
            last_notified_effective_price is null
            or last_notified_effective_price >= 0
        )
);


create index if not exists idx_watch_evaluation_state_condition_met
    on public.watch_evaluation_state(condition_met);


create index if not exists idx_watch_evaluation_state_last_evaluated
    on public.watch_evaluation_state(last_evaluated_at desc);


-- ============================================================
-- Notification Preferences
--
-- One row per user.
--
-- Email is the initial stable notification channel.
--
-- Other channels remain optional and can additionally require
-- feature entitlement.
-- ============================================================

create table if not exists public.notification_preferences (
    user_id uuid primary key
        references public.profiles(id)
        on delete cascade,

    email_enabled boolean not null default true,

    email_address text,

    push_enabled boolean not null default false,

    telegram_enabled boolean not null default false,

    whatsapp_enabled boolean not null default false,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);


drop trigger if exists trg_notification_preferences_set_updated_at
    on public.notification_preferences;


create trigger trg_notification_preferences_set_updated_at
before update on public.notification_preferences
for each row
execute function public.set_updated_at();


-- ============================================================
-- Notifications
--
-- Represents a meaningful notification generated by purchase
-- intelligence.
--
-- This is separate from actual delivery attempts.
--
-- Example:
--
-- notification:
--
-- "UK 9 is back in stock and the price dropped below your
-- ₹18,000 target."
--
-- delivery:
--
-- Resend email attempt
-- Telegram attempt
-- etc.
-- ============================================================

create table if not exists public.notifications (
    id uuid primary key default gen_random_uuid(),

    user_id uuid not null
        references public.profiles(id)
        on delete cascade,

    watch_id uuid
        references public.watch_intents(id)
        on delete set null,

    type text not null,

    title text not null,

    body text not null,

    payload jsonb not null
        default '{}'::jsonb,

    dedupe_key text,

    created_at timestamptz not null default now()
);


create index if not exists idx_notifications_user_id
    on public.notifications(user_id);


create index if not exists idx_notifications_watch_id
    on public.notifications(watch_id);


create index if not exists idx_notifications_created_at
    on public.notifications(created_at desc);


create index if not exists idx_notifications_user_created
    on public.notifications(
        user_id,
        created_at desc
    );


create index if not exists idx_notifications_dedupe_key
    on public.notifications(dedupe_key)
    where dedupe_key is not null;


-- ============================================================
-- Notification Deliveries
--
-- Provider/channel-specific delivery state.
--
-- Keeping this separate prevents Resend/Telegram/WhatsApp
-- details from leaking into generic notification logic.
-- ============================================================

create table if not exists public.notification_deliveries (
    id uuid primary key default gen_random_uuid(),

    notification_id uuid not null
        references public.notifications(id)
        on delete cascade,

    channel text not null
        check (
            channel in (
                'email',
                'push',
                'telegram',
                'whatsapp'
            )
        ),

    status text not null default 'pending'
        check (
            status in (
                'pending',
                'sent',
                'delivered',
                'failed'
            )
        ),

    provider_message_id text,

    attempted_at timestamptz,

    delivered_at timestamptz,

    failure_reason text,

    created_at timestamptz not null default now()
);


create index if not exists idx_notification_deliveries_notification_id
    on public.notification_deliveries(notification_id);


create index if not exists idx_notification_deliveries_status
    on public.notification_deliveries(status);


create index if not exists idx_notification_deliveries_channel
    on public.notification_deliveries(channel);


create index if not exists idx_notification_deliveries_provider_message_id
    on public.notification_deliveries(provider_message_id)
    where provider_message_id is not null;


-- ============================================================
-- Feature Flags
--
-- Defines experimental/beta capabilities globally.
--
-- These are configuration definitions.
--
-- Whether an individual user is granted a feature is stored in:
--
--   user_feature_entitlements
-- ============================================================

create table if not exists public.feature_flags (
    key text primary key,

    description text,

    default_enabled boolean not null default false,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);


drop trigger if exists trg_feature_flags_set_updated_at
    on public.feature_flags;


create trigger trg_feature_flags_set_updated_at
before update on public.feature_flags
for each row
execute function public.set_updated_at();


-- ============================================================
-- User Feature Entitlements
--
-- Allows admins/super-admins to enable beta capabilities for
-- selected users without hardcoded email checks.
-- ============================================================

create table if not exists public.user_feature_entitlements (
    user_id uuid not null
        references public.profiles(id)
        on delete cascade,

    feature_key text not null
        references public.feature_flags(key)
        on delete cascade,

    enabled boolean not null default true,

    granted_by uuid
        references public.profiles(id)
        on delete set null,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    primary key (
        user_id,
        feature_key
    )
);


create index if not exists idx_user_feature_entitlements_feature_key
    on public.user_feature_entitlements(feature_key);


create index if not exists idx_user_feature_entitlements_granted_by
    on public.user_feature_entitlements(granted_by);


drop trigger if exists trg_user_feature_entitlements_set_updated_at
    on public.user_feature_entitlements;


create trigger trg_user_feature_entitlements_set_updated_at
before update on public.user_feature_entitlements
for each row
execute function public.set_updated_at();


-- ============================================================
-- Initial Feature Definitions
--
-- All experimental capabilities remain disabled by default.
--
-- Per-user grants can be added after authentication/admin
-- architecture is active.
-- ============================================================

insert into public.feature_flags (
    key,
    description,
    default_enabled
)
values
    (
        'finance_intelligence',
        'Optional personal finance purchase intelligence.',
        false
    ),
    (
        'push_notifications',
        'Experimental push notification delivery.',
        false
    ),
    (
        'telegram_notifications',
        'Experimental Telegram notification delivery.',
        false
    ),
    (
        'whatsapp_notifications',
        'Experimental WhatsApp notification delivery.',
        false
    ),
    (
        'experimental_ai',
        'Experimental AI-assisted purchase intelligence features.',
        false
    ),
    (
        'price_prediction',
        'Experimental learned price prediction capabilities.',
        false
    )
on conflict (key) do nothing;


-- ============================================================
-- RLS
--
-- Policies are intentionally NOT added yet.
--
-- RLS enabled + no policy means normal anon/authenticated
-- Supabase clients cannot access these tables.
--
-- Trusted service-role operations continue to bypass RLS.
--
-- User-scoped policies arrive with the Auth/RLS milestone.
-- ============================================================

alter table public.watch_intents
    enable row level security;


alter table public.watch_listing_targets
    enable row level security;


alter table public.watch_evaluation_state
    enable row level security;


alter table public.notification_preferences
    enable row level security;


alter table public.notifications
    enable row level security;


alter table public.notification_deliveries
    enable row level security;


alter table public.feature_flags
    enable row level security;


alter table public.user_feature_entitlements
    enable row level security;

