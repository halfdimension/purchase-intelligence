export type ProductVariant = {
  size: string;
  current_price: number | null;
  in_stock: boolean;
  stock_remaining: number | null;
};

export type WatchlistItem = {
  id: string;
  email: string | null;
  desired_size: string | null;
  target_price: number | null;
  created_at: string;
  products: {
    id: string;
    url: string;
    brand: string;
    name: string | null;
    currency: string | null;
    mrp: number | null;
    current_price: number | null;
    image_url: string | null;
    in_stock: boolean | null;
    last_checked_at: string | null;
    product_variants: ProductVariant[];
  };
};

type JsonObject = Record<string, unknown>;

type Phase1ListingVariant = {
  id: string;
  canonical_variant_id: string | null;
  external_sku: string | null;
  title: string | null;
  attributes: JsonObject | null;
  variant_key: string | null;
  current_mrp: number | null;
  current_price: number | null;
  currency: string | null;
  in_stock: boolean;
  stock_remaining: number | null;
  last_checked_at: string | null;
};

type Phase1MerchantListing = {
  id: string;
  url: string;
  title: string | null;
  image_url: string | null;
  seller_name: string | null;
  current_mrp: number | null;
  current_price: number | null;
  currency: string | null;
  in_stock: boolean;
  last_checked_at: string | null;
  variants: Phase1ListingVariant[];
  merchant: {
    id: string;
    slug: string;
    name: string;
    base_url: string | null;
    adapter_key: string | null;
  } | null;
};

export type Phase1WatchIntent = {
  id: string;
  user_id: string;
  product_id: string;
  canonical_variant_id: string | null;
  tracking_scope: string;
  target_price: number | null;
  currency: string;
  variant_requirements: JsonObject | null;
  conditions: JsonObject | null;
  status: string;
  created_at: string;
  updated_at: string;

  product: {
    id: string;
    name: string;
    image_url: string | null;
    brand_id: string | null;
    category_id: string | null;
  } | null;

  canonical_variant: {
    id: string;
    title: string | null;
    canonical_sku: string | null;
    attributes: JsonObject | null;
    variant_key: string | null;
    image_url: string | null;
  } | null;

  evaluation: {
    condition_met: boolean;
    last_reason: string | null;
    state: JsonObject;
    last_evaluated_at: string | null;
    last_notified_at: string | null;
    last_notified_effective_price: number | null;
  } | null;

  listing_targets: Array<{
    listing_id: string;
    created_at: string;
    listing: Phase1MerchantListing | null;
  }>;
};

function stringAttribute(
  value: JsonObject | null | undefined,
  key: string,
) {
  const attribute = value?.[key];

  return typeof attribute === "string"
    ? attribute
    : null;
}

export function mapPhase1WatchToWatchlistItem(
  watch: Phase1WatchIntent,
): WatchlistItem {
  const listing =
    watch.listing_targets.find(
      (target) => target.listing !== null,
    )?.listing ?? null;

  const watchedVariant =
    listing?.variants.find(
      (variant) =>
        variant.canonical_variant_id ===
        watch.canonical_variant_id,
    ) ?? null;

  const desiredSize =
    stringAttribute(
      watch.canonical_variant?.attributes,
      "size",
    ) ??
    stringAttribute(
      watch.variant_requirements,
      "size",
    );

  const variants: ProductVariant[] =
    listing?.variants.map((variant) => ({
      size:
        stringAttribute(
          variant.attributes,
          "size",
        ) ??
        variant.title ??
        "Unknown",
      current_price: variant.current_price,
      in_stock: variant.in_stock,
      stock_remaining: variant.stock_remaining,
    })) ?? [];

  return {
    id: watch.id,

    // Phase 1 notifications belong to the authenticated account,
    // rather than storing an email address on each watch.
    email: null,

    desired_size: desiredSize,
    target_price: watch.target_price,
    created_at: watch.created_at,

    products: {
      id: watch.product_id,
      url: listing?.url ?? "",
      brand:
        listing?.seller_name ??
        listing?.merchant?.name ??
        "Unknown merchant",
      name:
        watch.product?.name ??
        listing?.title ??
        null,
      currency:
        watchedVariant?.currency ??
        listing?.currency ??
        watch.currency,
      mrp:
        watchedVariant?.current_mrp ??
        listing?.current_mrp ??
        null,
      current_price:
        watchedVariant?.current_price ??
        listing?.current_price ??
        null,
      image_url:
        watch.product?.image_url ??
        listing?.image_url ??
        null,
      in_stock:
        listing?.in_stock ?? null,
      last_checked_at:
        watchedVariant?.last_checked_at ??
        listing?.last_checked_at ??
        null,
      product_variants: variants,
    },
  };
}
