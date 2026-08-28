import argparse
import json
from urllib.parse import urlparse

import requests

from crawler.scrapers.browser_jsonld import BrowserJsonLdScraper
from crawler.scrapers.generic_jsonld import GenericJsonLdScraper
from crawler.scrapers.nike import NikeScraper


def choose_scraper(url: str):
    hostname = (
        urlparse(url).hostname or ""
    ).lower()

    if "nike." in hostname:
        return NikeScraper()

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Extract product information from a product URL."
    )

    parser.add_argument(
        "url",
        help="Product page URL",
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="Save extracted product data to Supabase.",
    )

    args = parser.parse_args()

    try:
        scraper = choose_scraper(
            args.url
        )

        if scraper is not None:
            print(
                "Using retailer-specific scraper: Nike\n"
            )

            product = scraper.scrape(
                args.url
            )

        else:
            try:
                print(
                    "Trying standard HTTP scraper...\n"
                )

                scraper = GenericJsonLdScraper()

                product = scraper.scrape(
                    args.url
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
                    "\nStandard request received 403."
                )

                print(
                    "Falling back to browser rendering...\n"
                )

                scraper = BrowserJsonLdScraper()

                product = scraper.scrape(
                    args.url
                )

        print("\nNormalized product:")

        print(
            json.dumps(
                product.to_dict(),
                indent=2,
                ensure_ascii=False,
            )
        )

        if args.save:
            from crawler.database import save_product

            print("\nSaving product to Supabase...")

            saved_product = save_product(product)

            print(
                "Saved product ID:",
                saved_product["id"],
            )

            print("Price snapshot saved.")

            print(
                f"Variants saved: {len(product.variants)}"
            )

    except Exception as exc:
        print(
            f"\nCrawler failed: {exc}"
        )

        raise SystemExit(1)


if __name__ == "__main__":
    main()
