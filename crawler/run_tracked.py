from urllib.parse import urlparse

import requests

from crawler.alerts import evaluate_watch
from crawler.database import (
    get_tracked_products,
    get_watchlists_for_product,
    get_watch_alert_state,
    save_product,
    save_watch_alert_state,
)
from crawler.emailer import send_price_alert
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

            watches = get_watchlists_for_product(
                saved_product["id"]
            )

            print()
            print(
                f"Watch conditions: {len(watches)}"
            )

            for watch in watches:
                evaluation = evaluate_watch(
                    watch,
                    product,
                )

                print()
                print(
                    f"Email: {evaluation.email}"
                )

                print(
                    f"Desired size: "
                    f"{evaluation.desired_size or 'Any'}"
                )

                print(
                    f"Target price: "
                    f"{evaluation.target_price}"
                )

                print(
                    f"Current price: "
                    f"{evaluation.current_price}"
                )

                print(
                    f"Size available: "
                    f"{evaluation.size_available}"
                )

                print(
                    f"Price target reached: "
                    f"{evaluation.price_target_reached}"
                )

                if evaluation.should_alert:
                    print(
                        "Result: ALERT READY"
                    )
                else:
                    print(
                        "Result: WAIT"
                    )

                print(
                    f"Reason: {evaluation.reason}"
                )

                previous_state = get_watch_alert_state(
                    watch["id"]
                )

                previous_condition_met = (
                    previous_state is not None
                    and previous_state.get(
                        "condition_met"
                    ) is True
                )

                if evaluation.should_alert:
                    if not previous_condition_met:
                        print(
                            "Sending email alert..."
                        )

                        result = send_price_alert(
                            recipient=evaluation.email,
                            product_name=(
                                product.name
                                or product.brand
                                or "Tracked product"
                            ),
                            product_url=product.url,
                            desired_size=(
                                evaluation.desired_size
                            ),
                            current_price=(
                                evaluation.current_price
                            ),
                            target_price=(
                                evaluation.target_price
                            ),
                        )

                        print(
                            "Email sent:",
                            result.get("id"),
                        )

                        save_watch_alert_state(
                            watchlist_id=watch["id"],
                            condition_met=True,
                            reason=evaluation.reason,
                            notified=True,
                            notified_price=(
                                evaluation.current_price
                            ),
                        )

                    else:
                        print(
                            "Alert already sent. "
                            "Skipping duplicate email."
                        )

                        save_watch_alert_state(
                            watchlist_id=watch["id"],
                            condition_met=True,
                            reason=evaluation.reason,
                        )

                else:
                    save_watch_alert_state(
                        watchlist_id=watch["id"],
                        condition_met=False,
                        reason=evaluation.reason,
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
