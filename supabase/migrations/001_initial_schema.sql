create extension if not exists pgcrypto;

create table if not exists products (
    id uuid primary key default gen_random_uuid(),

    url text not null unique,
    brand text not null,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists watchlists (
    id uuid primary key default gen_random_uuid(),

    product_id uuid not null
        references products(id)
        on delete cascade,

    email text not null,
    desired_size text,
    target_price numeric(12, 2),

    created_at timestamptz not null default now(),

    unique(product_id, email)
);

create index if not exists idx_watchlists_email
    on watchlists(email);

create index if not exists idx_watchlists_product_id
    on watchlists(product_id);
