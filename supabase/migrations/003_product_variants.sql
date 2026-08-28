create table if not exists product_variants (
    id uuid primary key default gen_random_uuid(),

    product_id uuid not null
        references products(id)
        on delete cascade,

    size text not null,
    sku text,

    mrp numeric(12, 2),
    current_price numeric(12, 2),

    in_stock boolean,
    stock_remaining integer,

    last_checked_at timestamptz not null default now(),

    unique(product_id, size)
);

create index if not exists idx_product_variants_product_id
    on product_variants(product_id);

create index if not exists idx_product_variants_sku
    on product_variants(sku);
