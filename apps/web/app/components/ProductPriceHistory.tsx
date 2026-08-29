"use client";

import { useEffect, useMemo, useState } from "react";

type PriceSnapshot = {
  id: string;
  mrp: number | null;
  selling_price: number | null;
  currency: string;
  in_stock: boolean | null;
  checked_at: string;
};

type HistoryResponse = {
  product_id: string;
  stats: {
    lowest_price: number | null;
    highest_price: number | null;
    latest_price: number | null;
    snapshot_count: number;
  };
  history: PriceSnapshot[];
};

type Props = {
  productId: string;
  currency: string | null;
  targetPrice: number | null;
};

function formatPrice(
  value: number | null,
  currency: string | null,
) {
  if (value === null) {
    return "—";
  }

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: currency || "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
  }).format(new Date(value));
}

export function ProductPriceHistory({
  productId,
  currency,
  targetPrice,
}: Props) {
  const [data, setData] = useState<HistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadHistory() {
      try {
        const response = await fetch(
          `/api/products/${productId}/history`,
        );

        const result = await response.json();

        if (!response.ok) {
          throw new Error(
            result.error || "Failed to load price history.",
          );
        }

        if (!cancelled) {
          setData(result);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load price history.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadHistory();

    return () => {
      cancelled = true;
    };
  }, [productId]);

  const chart = useMemo(() => {
    if (!data) {
      return null;
    }

    const snapshots = data.history.filter(
      (snapshot) =>
        typeof snapshot.selling_price === "number",
    );

    if (snapshots.length === 0) {
      return null;
    }

    const width = 700;
    const height = 180;
    const paddingX = 12;
    const paddingY = 18;

    const observedPrices = snapshots.map(
      (snapshot) => snapshot.selling_price as number,
    );

    const domainPrices =
      targetPrice !== null
        ? [...observedPrices, targetPrice]
        : observedPrices;

    let minPrice = Math.min(...domainPrices);
    let maxPrice = Math.max(...domainPrices);

    if (minPrice === maxPrice) {
      minPrice -= 1;
      maxPrice += 1;
    }

    const xForIndex = (index: number) => {
      if (snapshots.length === 1) {
        return width / 2;
      }

      return (
        paddingX +
        (index / (snapshots.length - 1)) *
          (width - paddingX * 2)
      );
    };

    const yForPrice = (price: number) =>
      paddingY +
      ((maxPrice - price) / (maxPrice - minPrice)) *
        (height - paddingY * 2);

    const points = snapshots
      .map(
        (snapshot, index) =>
          `${xForIndex(index)},${yForPrice(
            snapshot.selling_price as number,
          )}`,
      )
      .join(" ");

    return {
      width,
      height,
      points,
      snapshots,
      targetY:
        targetPrice !== null
          ? yForPrice(targetPrice)
          : null,
    };
  }, [data, targetPrice]);

  if (loading) {
    return (
      <div className="border-t border-zinc-800 pt-5 text-sm text-zinc-600">
        Loading price history...
      </div>
    );
  }

  if (error) {
    return (
      <div className="border-t border-zinc-800 pt-5 text-sm text-red-400">
        {error}
      </div>
    );
  }

  if (!data || data.history.length === 0) {
    return (
      <div className="border-t border-zinc-800 pt-5 text-sm text-zinc-600">
        No price history yet.
      </div>
    );
  }

  return (
    <div className="border-t border-zinc-800 pt-5">
      <div className="mb-5 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h4 className="font-medium text-zinc-200">
            Price history
          </h4>

          <p className="mt-1 text-xs text-zinc-600">
            Automatically recorded by each crawler check.
          </p>
        </div>

        <span className="text-xs text-zinc-600">
          {data.stats.snapshot_count} checks
        </span>
      </div>

      <div className="mb-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div>
          <span className="text-xs uppercase tracking-wide text-zinc-600">
            Lowest seen
          </span>

          <p className="mt-1 text-sm text-zinc-300">
            {formatPrice(
              data.stats.lowest_price,
              currency,
            )}
          </p>
        </div>

        <div>
          <span className="text-xs uppercase tracking-wide text-zinc-600">
            Highest seen
          </span>

          <p className="mt-1 text-sm text-zinc-300">
            {formatPrice(
              data.stats.highest_price,
              currency,
            )}
          </p>
        </div>

        <div>
          <span className="text-xs uppercase tracking-wide text-zinc-600">
            Latest
          </span>

          <p className="mt-1 text-sm text-zinc-300">
            {formatPrice(
              data.stats.latest_price,
              currency,
            )}
          </p>
        </div>

        <div>
          <span className="text-xs uppercase tracking-wide text-zinc-600">
            Target
          </span>

          <p className="mt-1 text-sm text-zinc-300">
            {targetPrice !== null
              ? formatPrice(targetPrice, currency)
              : "Any drop"}
          </p>
        </div>
      </div>

      {chart && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4">
          <svg
            viewBox={`0 0 ${chart.width} ${chart.height}`}
            className="h-40 w-full"
            role="img"
            aria-label="Historical product price chart"
          >
            {chart.targetY !== null && (
              <line
                x1="0"
                x2={chart.width}
                y1={chart.targetY}
                y2={chart.targetY}
                stroke="currentColor"
                strokeDasharray="8 8"
                className="text-emerald-800"
              />
            )}

            <polyline
              points={chart.points}
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinejoin="round"
              strokeLinecap="round"
              className="text-zinc-200"
            />
          </svg>

          <div className="mt-2 flex justify-between text-xs text-zinc-600">
            <span>
              {formatShortDate(
                chart.snapshots[0].checked_at,
              )}
            </span>

            {targetPrice !== null && (
              <span className="text-emerald-700">
                Target{" "}
                {formatPrice(targetPrice, currency)}
              </span>
            )}

            <span>
              {formatShortDate(
                chart.snapshots[
                  chart.snapshots.length - 1
                ].checked_at,
              )}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
