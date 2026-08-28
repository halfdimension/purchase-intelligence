import re
import sys

from playwright.sync_api import sync_playwright


if len(sys.argv) != 2:
    print("Usage: python -m crawler.debug_product_page <url>")
    raise SystemExit(1)

url = sys.argv[1]

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)

    page = browser.new_page(locale="en-IN")

    response = page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(5000)

    print("HTTP status:", response.status if response else None)
    print("Final URL:", page.url)
    print("Title:", page.title())

    html = page.content()
    body_text = page.locator("body").inner_text()

    browser.close()


print("\n========== VISIBLE PRICE / SIZE TEXT ==========\n")

interesting_lines = []

for raw_line in body_text.splitlines():
    line = raw_line.strip()

    if not line:
        continue

    lower = line.lower()

    if (
        "₹" in line
        or "mrp" in lower
        or "size" in lower
        or re.search(r"\buk\s*\d", lower)
        or "stock" in lower
    ):
        interesting_lines.append(line)

for line in interesting_lines[:150]:
    print(line)


print("\n========== HTML KEY SNIPPETS ==========\n")

patterns = [
    "mrp",
    "price",
    "sellingPrice",
    "discountedPrice",
    "finalPrice",
    "size",
    "sizes",
    "inventory",
    "stock",
    "availability",
]

lower_html = html.lower()

seen = set()

for pattern in patterns:
    search_pattern = pattern.lower()
    start = 0
    count = 0

    while count < 5:
        index = lower_html.find(search_pattern, start)

        if index == -1:
            break

        left = max(0, index - 180)
        right = min(len(html), index + 350)

        snippet = html[left:right].replace("\n", " ")

        if snippet not in seen:
            seen.add(snippet)

            print(f"\n--- {pattern} ---")
            print(snippet[:550])

            count += 1

        start = index + len(search_pattern)


with open("/tmp/product-debug.html", "w", encoding="utf-8") as output:
    output.write(html)

print("\nRendered HTML saved to:")
print("/tmp/product-debug.html")
