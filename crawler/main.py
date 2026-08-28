import argparse
import json

import requests

from crawler.scrapers.browser_jsonld import BrowserJsonLdScraper
from crawler.scrapers.generic_jsonld import GenericJsonLdScraper


def main():
    parser = argparse.ArgumentParser(
        description="Extract product information from a product URL."
    )

    parser.add_argument(
        "url",
        help="Product page URL",
    )

    args = parser.parse_args()

    try:
        try:
            print("Trying standard HTTP scraper...\n")

            scraper = GenericJsonLdScraper()
            product = scraper.scrape(args.url)

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
            product = scraper.scrape(args.url)

        print("\nNormalized product:")

        print(
            json.dumps(
                product.to_dict(),
                indent=2,
                ensure_ascii=False,
            )
        )

    except Exception as exc:
        print(
            f"\nCrawler failed: {exc}"
        )

        raise SystemExit(1)


if __name__ == "__main__":
    main()
