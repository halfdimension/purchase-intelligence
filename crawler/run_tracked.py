from urllib.parse import urlparse

import requests

from crawler.database import (
    get_tracked_products,
    save_product,
)
from crawler.scrapers.browser_jsonld import BrowserJsonLdScraper
from crawler.scrapers.generic_jsonld import GenericJsonLdScraper
from crawler.scrapers.nike import NikeScraper


def scrape_product(url: str):
    hostname = (
        urlparse(url).hostname or ""
    ).lower()

    if "nike." in hostname:
        print(
            "Using retailer-specific scraper: Nike"
        )

        return NikeScraper().scrape(url)

    try:
        print(
            "Using generic HTTP scraper"
        )

        return GenericJsonLdScraper().scrape(
            url
        )

    except requests.HTTPError as exc:
        status_code = (
            exc.response.status_code
            if exc.response is not None
            else None
        )

        if status_code != 403:
            raise

        print(
            "HTTP request returned 403."
        )
        print(
            "Falling back to Playwright."
        )

        return BrowserJsonLdScraper().scrape(
            url
        )


def main():
    tracked_products = get_tracked_products()

    if not tracked_products:
        print("No tracked products found.")
        return

    print(
        f"Found {len(tracked_products)} "
        "unique tracked product(s)."
    )

    succeeded = 0
    failed = 0

    for index, tracked in enumerate(
        tracked_products,
        start=1,
    ):
        url = tracked["url"]

        name = (
            tracked.get("name")
            or tracked.get("brand")
            or url
        )

        print()
        print(
            "=" * 70
        )
        print(
            f"[{index}/{len(tracked_products)}] "
            f"{name}"
        )
        print(url)
        print(
            "=" * 70
        )

        try:
            product = scrape_product(
                url
            )

            saved_product = save_product(
                product
            )

            print()
            print(
                "Saved product:",
                saved_product["id"],
            )

            print(
                "Current price:",
                product.current_price,
            )

            print(
                "MRP:",
                product.mrp,
            )

            print(
                "Variants:",
                len(product.variants),
            )

            succeeded += 1

        except Exception as exc:
            failed += 1

            print()
            print(
                f"FAILED: {exc}"
            )

    print()
    print(
        "=" * 70
    )
    print("Crawler run complete")
    print(
        f"Succeeded: {succeeded}"
    )
    print(
        f"Failed:    {failed}"
    )
    print(
        "=" * 70
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
