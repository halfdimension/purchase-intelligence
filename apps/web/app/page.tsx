export default function Home() {
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-10 lg:px-8">
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
            Watchlist
          </div>
        </header>

        <section className="grid flex-1 items-center gap-12 lg:grid-cols-2">
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
              <h3 className="text-2xl font-semibold">Track a product</h3>
              <p className="mt-2 text-sm text-zinc-500">
                Start with an Adidas, Nike or ASICS product URL.
              </p>
            </div>

            <form className="space-y-5">
              <div>
                <label
                  htmlFor="productUrl"
                  className="mb-2 block text-sm font-medium text-zinc-300"
                >
                  Product URL
                </label>

                <input
                  id="productUrl"
                  name="productUrl"
                  type="url"
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
                    name="size"
                    defaultValue=""
                    className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm outline-none transition focus:border-zinc-500"
                  >
                    <option value="" disabled>
                      Select size
                    </option>
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
                    name="targetPrice"
                    type="number"
                    min="0"
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
                  name="email"
                  type="email"
                  placeholder="you@example.com"
                  className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm outline-none transition placeholder:text-zinc-600 focus:border-zinc-500"
                />
              </div>

              <button
                type="submit"
                className="w-full rounded-xl bg-zinc-100 px-4 py-3 font-medium text-zinc-950 transition hover:bg-white"
              >
                Track Product
              </button>
            </form>

            <p className="mt-5 text-center text-xs text-zinc-600">
              Personal finance and AI recommendations will remain optional.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
