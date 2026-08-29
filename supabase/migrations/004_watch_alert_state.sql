create table if not exists watch_alert_state (
    watchlist_id uuid primary key
        references watchlists(id)
        on delete cascade,

    condition_met boolean not null default false,

    last_reason text,

    last_evaluated_at timestamptz not null default now(),

    last_notified_at timestamptz,

    last_notified_price numeric(12, 2)
);
