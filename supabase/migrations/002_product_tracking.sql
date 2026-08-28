alter table products
    add column if not exists name text,
    add column if not exists currency text,
    add column if not exists mrp numeric(12, 2),
    add column if not exists current_price numeric(12, 2),
    add column if not exists image_url text,
    add column if not exists in_stock boolean,
    add column if not exists last_checked_at timestamptz;

create table if not exists price_snapshots (
    id uuid primary key default gen_random_uuid(),

    product_id uuid not null
        references products(id)
        on delete cascade,

    mrp numeric(12, 2),
    selling_price numeric(12, 2),
    currency text not null default 'INR',
    in_stock boolean,

    checked_at timestamptz not null default now()
);

create index if not exists idx_price_snapshots_product_id
    on price_snapshots(product_id);

create index if not exists idx_price_snapshots_checked_at
    on price_snapshots(checked_at desc);

create index if not exists idx_price_snapshots_product_checked
    on price_snapshots(product_id, checked_at desc);
