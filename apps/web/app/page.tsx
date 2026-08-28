"use client";

import { FormEvent, useEffect, useState } from "react";

type WatchlistItem = {
  id: string;
  email: string;
  desired_size: string | null;
  target_price: number | null;
  created_at: string;
  products: {
    id: string;
    url: string;
    brand: string;
  };
};

export default function Home() {
  const [productUrl, setProductUrl] = useState("");
  const [size, setSize] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [email, setEmail] = useState("");

  const [products, setProducts] = useState<WatchlistItem[]>([]);
  const [error, setError] = useState("");

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function loadWatchlist() {
      try {
        const response = await fetch("/api/watchlist");

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.error || "Failed to load watchlist.");
        }

        setProducts(data.watchlist);
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

    loadWatchlist();
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
      const response = await fetch(`/api/watchlist/${id}`, {
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
              Add a product you want to buy. We&apos;ll eventually monitor its
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
              {products.map((product) => (
                <article
                  key={product.id}
                  className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5"
                >
                  <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <div className="mb-3 flex items-center gap-3">
                        <span className="rounded-full border border-zinc-700 px-3 py-1 text-xs font-medium text-zinc-300">
                          {product.products.brand}
                        </span>

                        <span className="text-xs text-emerald-400">
                          Stored in database
                        </span>
                      </div>

                      <a
                        href={product.products.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block truncate text-sm text-zinc-300 underline decoration-zinc-700 underline-offset-4 hover:text-white"
                      >
                        {product.products.url}
                      </a>

                      <div className="mt-4 flex flex-wrap gap-x-8 gap-y-3 text-sm">
                        <div>
                          <span className="text-zinc-600">
                            Size
                          </span>

                          <p className="mt-1 text-zinc-300">
                            {product.desired_size || "Any"}
                          </p>
                        </div>

                        <div>
                          <span className="text-zinc-600">
                            Target price
                          </span>

                          <p className="mt-1 text-zinc-300">
                            {product.target_price !== null
                              ? `₹${Number(
                                  product.target_price,
                                ).toLocaleString("en-IN")}`
                              : "Any drop"}
                          </p>
                        </div>

                        <div>
                          <span className="text-zinc-600">
                            Notify
                          </span>

                          <p className="mt-1 text-zinc-300">
                            {product.email}
                          </p>
                        </div>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => removeProduct(product.id)}
                      className="cursor-pointer text-sm text-zinc-500 transition hover:text-red-400"
                    >
                      Remove
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
