"use client";

import { FormEvent, useEffect, useState } from "react";

import { ProductPriceHistory } from "@/app/components/ProductPriceHistory";
import {
  mapPhase1WatchToWatchlistItem,
  type Phase1WatchIntent,
  type WatchlistItem,
} from "@/lib/watch-intent-ui";

function formatPrice(
  value: number | null,
  currency: string | null = "INR",
) {
  if (value === null) {
    return "Not checked yet";
  }

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: currency || "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function normalizeSize(size: string) {
  const match = size.toUpperCase().match(/UK\s*\d+(?:\.\d+)?/);

  if (match) {
    return match[0].replace(/\s+/g, " ");
  }

  return size.trim().toUpperCase();
}

function getDesiredVariant(product: WatchlistItem) {
  if (!product.desired_size) {
    return null;
  }

  const desiredSize = normalizeSize(product.desired_size);

  return (
    product.products.product_variants.find(
      (variant) => normalizeSize(variant.size) === desiredSize,
    ) ?? null
  );
}

function formatLastChecked(value: string | null) {
  if (!value) {
    return "Waiting for first check";
  }

  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function Home() {
  const [productUrl, setProductUrl] = useState("");
  const [size, setSize] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [email, setEmail] = useState("");

  const [products, setProducts] = useState<WatchlistItem[]>([]);
  const [accountEmail, setAccountEmail] = useState<string | null>(null);
  const [error, setError] = useState("");

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function loadWatchlist() {
      try {
        const response = await fetch("/api/watch-intents");

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.error || "Failed to load watchlist.");
        }

        if (!Array.isArray(data.watches)) {
          throw new Error("Invalid watchlist response.");
        }

        setProducts(
          (data.watches as Phase1WatchIntent[]).map(
            mapPhase1WatchToWatchlistItem,
          ),
        );
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load watchlist.",
        );
      } finally {
        setLoading(false);
      }
    }

    async function loadProfile() {
      try {
        const response = await fetch("/api/profile/me");

        if (!response.ok) {
          return;
        }

        const data = await response.json();

        if (
          data.profile &&
          typeof data.profile.email === "string"
        ) {
          setAccountEmail(data.profile.email);
        }
      } catch {
        // Watchlist rendering should not fail if profile metadata
        // cannot be loaded.
      }
    }

    loadWatchlist();
    loadProfile();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setError("");

    if (!productUrl.trim()) {
      setError("Product URL is required.");
      return;
    }

    try {
      new URL(productUrl);
    } catch {
      setError("Enter a valid product URL.");
      return;
    }

    if (!email.trim()) {
      setError("Email is required.");
      return;
    }

    if (targetPrice && Number(targetPrice) <= 0) {
      setError("Target price must be greater than 0.");
      return;
    }

    try {
      setSubmitting(true);

      const response = await fetch("/api/watchlist", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          productUrl,
          size,
          targetPrice,
          email,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.error || "Failed to track product.",
        );
      }

      setProducts((currentProducts) => [
        data.watchlistItem,
        ...currentProducts,
      ]);

      setProductUrl("");
      setSize("");
      setTargetPrice("");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to track product.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function removeProduct(id: string) {
    setError("");

    try {
      const response = await fetch(`/api/watch-intents/${id}`, {
        method: "DELETE",
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.error || "Failed to remove product.",
        );
      }

      setProducts((currentProducts) =>
        currentProducts.filter((product) => product.id !== id),
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to remove product.",
      );
    }
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto min-h-screen max-w-6xl px-6 py-10 lg:px-8">
        <header className="mb-16 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              Purchase Intelligence
            </h1>

            <p className="mt-1 text-sm text-zinc-500">
              Track prices. Find better deals. Buy at the right time.
            </p>
          </div>

          <div className="rounded-full border border-zinc-800 px-4 py-2 text-sm text-zinc-400">
            Watchlist {products.length > 0 && `(${products.length})`}
          </div>
        </header>

        <section className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <p className="mb-4 text-sm font-medium uppercase tracking-[0.2em] text-zinc-500">
              Smarter purchasing
            </p>

            <h2 className="max-w-xl text-4xl font-semibold tracking-tight sm:text-5xl">
              Stop checking prices manually.
            </h2>

            <p className="mt-6 max-w-lg text-base leading-7 text-zinc-400">
              Add a product you want to buy. We&apos;ll monitor its
              price, stock, offers and historical lows and tell you when it
              becomes worth buying.
            </p>

            <div className="mt-8 flex flex-wrap gap-3 text-sm text-zinc-400">
              <span className="rounded-full border border-zinc-800 px-3 py-1.5">
                Price tracking
              </span>

              <span className="rounded-full border border-zinc-800 px-3 py-1.5">
                Size availability
              </span>

              <span className="rounded-full border border-zinc-800 px-3 py-1.5">
                Offer analysis
              </span>

              <span className="rounded-full border border-zinc-800 px-3 py-1.5">
                Buy / Wait advice
              </span>
            </div>
          </div>

          <div className="rounded-3xl border border-zinc-800 bg-zinc-900/60 p-6 shadow-2xl shadow-black/20 sm:p-8">
            <div className="mb-8">
              <h3 className="text-2xl font-semibold">
                Track a product
              </h3>

              <p className="mt-2 text-sm text-zinc-500">
                Start with an Adidas, Nike or ASICS product URL.
              </p>
            </div>

            <form
              className="space-y-5"
              onSubmit={handleSubmit}
            >
              <div>
                <label
                  htmlFor="productUrl"
                  className="mb-2 block text-sm font-medium text-zinc-300"
                >
                  Product URL
                </label>

                <input
                  id="productUrl"
                  type="url"
                  value={productUrl}
                  onChange={(event) =>
                    setProductUrl(event.target.value)
                  }
                  placeholder="https://www.asics.co.in/..."
                  className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm outline-none transition placeholder:text-zinc-600 focus:border-zinc-500"
                />
              </div>

              <div className="grid gap-5 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="size"
                    className="mb-2 block text-sm font-medium text-zinc-300"
                  >
                    Your size
                  </label>

                  <select
                    id="size"
                    value={size}
                    onChange={(event) =>
                      setSize(event.target.value)
                    }
                    className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm outline-none transition focus:border-zinc-500"
                  >
                    <option value="">Select size</option>
                    <option value="UK 7">UK 7</option>
                    <option value="UK 8">UK 8</option>
                    <option value="UK 9">UK 9</option>
                    <option value="UK 10">UK 10</option>
                    <option value="UK 11">UK 11</option>
                  </select>
                </div>

                <div>
                  <label
                    htmlFor="targetPrice"
                    className="mb-2 block text-sm font-medium text-zinc-300"
                  >
                    Target price
                  </label>

                  <input
                    id="targetPrice"
                    type="number"
                    min="1"
                    value={targetPrice}
                    onChange={(event) =>
                      setTargetPrice(event.target.value)
                    }
                    placeholder="₹ 8000"
                    className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm outline-none transition placeholder:text-zinc-600 focus:border-zinc-500"
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="email"
                  className="mb-2 block text-sm font-medium text-zinc-300"
                >
                  Email
                </label>

                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(event) =>
                    setEmail(event.target.value)
                  }
                  placeholder="you@example.com"
                  className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm outline-none transition placeholder:text-zinc-600 focus:border-zinc-500"
                />
              </div>

              {error && (
                <div className="rounded-xl border border-red-900/70 bg-red-950/30 px-4 py-3 text-sm text-red-300">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="w-full cursor-pointer rounded-xl bg-zinc-100 px-4 py-3 font-medium text-zinc-950 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting
                  ? "Adding Product..."
                  : "Track Product"}
              </button>
            </form>

            <p className="mt-5 text-center text-xs text-zinc-600">
              Personal finance and AI recommendations will remain optional.
            </p>
          </div>
        </section>

        <section className="mt-20 border-t border-zinc-900 pt-10">
          <div className="mb-6">
            <h2 className="text-2xl font-semibold">
              Your watchlist
            </h2>

            <p className="mt-2 text-sm text-zinc-500">
              Products stored in your persistent watchlist.
            </p>
          </div>

          {loading ? (
            <div className="rounded-2xl border border-zinc-800 px-6 py-12 text-center text-zinc-500">
              Loading watchlist...
            </div>
          ) : products.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-zinc-800 px-6 py-12 text-center">
              <p className="text-zinc-400">
                No products tracked yet.
              </p>

              <p className="mt-2 text-sm text-zinc-600">
                Add your first product using the form above.
              </p>
            </div>
          ) : (
            <div className="grid gap-4">
              {products.map((product) => {
                const desiredVariant = getDesiredVariant(product);

                const sizeAvailable = product.desired_size
                  ? desiredVariant?.in_stock ?? false
                  : product.products.in_stock ?? false;

                return (
                  <article
                    key={product.id}
                    className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5"
                  >
                    <div className="flex flex-col gap-6">
                      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                        <div className="min-w-0">
                          <div className="mb-3 flex flex-wrap items-center gap-3">
                            <span className="rounded-full border border-zinc-700 px-3 py-1 text-xs font-medium text-zinc-300">
                              {product.products.brand}
                            </span>

                            <span
                              className={`text-xs ${
                                sizeAvailable
                                  ? "text-emerald-400"
                                  : "text-amber-400"
                              }`}
                            >
                              {product.desired_size
                                ? `${product.desired_size} ${
                                    sizeAvailable
                                      ? "in stock"
                                      : "out of stock"
                                  }`
                                : product.products.in_stock
                                  ? "In stock"
                                  : "Out of stock"}
                            </span>
                          </div>

                          <h3 className="text-lg font-semibold text-zinc-100">
                            {product.products.name ||
                              `${product.products.brand} product`}
                          </h3>

                          <a
                            href={product.products.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="mt-2 block truncate text-sm text-zinc-500 underline decoration-zinc-700 underline-offset-4 hover:text-zinc-300"
                          >
                            {product.products.url}
                          </a>
                        </div>

                        <button
                          type="button"
                          onClick={() => removeProduct(product.id)}
                          className="cursor-pointer text-sm text-zinc-500 transition hover:text-red-400"
                        >
                          Remove
                        </button>
                      </div>

                      <div className="grid gap-4 border-t border-zinc-800 pt-5 sm:grid-cols-2 lg:grid-cols-4">
                        <div>
                          <span className="text-xs uppercase tracking-wide text-zinc-600">
                            Current price
                          </span>

                          <p className="mt-1 text-lg font-semibold text-zinc-100">
                            {formatPrice(
                              product.products.current_price,
                              product.products.currency,
                            )}
                          </p>
                        </div>

                        <div>
                          <span className="text-xs uppercase tracking-wide text-zinc-600">
                            MRP
                          </span>

                          <p className="mt-1 text-zinc-300">
                            {formatPrice(
                              product.products.mrp,
                              product.products.currency,
                            )}
                          </p>
                        </div>

                        <div>
                          <span className="text-xs uppercase tracking-wide text-zinc-600">
                            Your target
                          </span>

                          <p className="mt-1 text-zinc-300">
                            {product.target_price !== null
                              ? formatPrice(
                                  product.target_price,
                                  product.products.currency,
                                )
                              : "Any drop"}
                          </p>
                        </div>

                        <div>
                          <span className="text-xs uppercase tracking-wide text-zinc-600">
                            Desired size
                          </span>

                          <p className="mt-1 text-zinc-300">
                            {product.desired_size || "Any"}
                          </p>

                          {desiredVariant?.stock_remaining !== null &&
                            desiredVariant?.stock_remaining !== undefined && (
                              <p className="mt-1 text-xs text-amber-400">
                                {desiredVariant.stock_remaining} remaining
                              </p>
                            )}
                        </div>
                      </div>

                      <ProductPriceHistory
                        productId={product.products.id}
                        currency={product.products.currency}
                        targetPrice={product.target_price}
                      />

                      <div className="flex flex-col gap-2 border-t border-zinc-800 pt-4 text-xs text-zinc-500 sm:flex-row sm:items-center sm:justify-between">
                        <span>
                          Last checked:{" "}
                          {formatLastChecked(
                            product.products.last_checked_at,
                          )}
                        </span>

                        <span>
                          Alerts: {accountEmail ?? "Account email"}
                        </span>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
