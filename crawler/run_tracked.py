from urllib.parse import urlparse

import requests

from crawler.alerts import evaluate_watch
from crawler.database import (
    get_watchlists_for_product,
    get_watch_alert_state,
    save_product,
    save_watch_alert_state,
)
from crawler.emailer import send_price_alert
from crawler.notification_runtime import (
    get_notification_runtime_mode,
)
from crawler.phase1_database import (
    get_phase1_crawl_targets,
    save_product_phase1,
)
from crawler.phase1_watch_database import (
    get_phase1_watches_for_listing,
)
from crawler.phase1_watch_processor import (
    process_phase1_watch,
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
    notification_mode = (
        get_notification_runtime_mode()
    )

    print(
        "Notification runtime mode:",
        notification_mode.name,
    )

    tracked_products = get_phase1_crawl_targets()

    if not tracked_products:
        print("No Phase 1 crawl targets found.")
        return

    print(
        f"Found {len(tracked_products)} "
        "unique Phase 1 crawl target(s)."
    )

    succeeded = 0
    failed = 0
    phase1_failed = 0

    for index, tracked in enumerate(
        tracked_products,
        start=1,
    ):
        url = tracked["url"]

        name = (
            tracked.get("title")
            or tracked.get("name")
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

            try:
                phase1_result = save_product_phase1(
                    product
                )

                print()
                print("Phase 1 persistence:")
                print(
                    "  Listing:",
                    phase1_result["listing"]["id"],
                )
                print(
                    "  Listing observation:",
                    phase1_result[
                        "listing_observation"
                    ]["id"],
                )
                print(
                    "  Variants:",
                    len(
                        phase1_result["variants"]
                    ),
                )
                print(
                    "  Variant observations:",
                    len(
                        phase1_result[
                            "variant_observations"
                        ]
                    ),
                )

                phase1_watches = (
                    get_phase1_watches_for_listing(
                        phase1_result["listing"]
                    )
                )

                print()
                print(
                    "Phase 1 watch evaluations:",
                    len(phase1_watches),
                )

                for watch_context in phase1_watches:
                    try:
                        phase1_watch_result = (
                            process_phase1_watch(
                                watch_context,
                                phase1_result["listing"],
                                product,
                                notification_execution_enabled=(
                                    notification_mode
                                    .phase1_notification_execution_enabled
                                ),
                            )
                        )

                        phase1_evaluation = (
                            phase1_watch_result.evaluation
                        )

                        phase1_decision = (
                            phase1_watch_result.decision
                        )

                        print()
                        print(
                            "  Phase 1 watch:",
                            phase1_evaluation.watch_id,
                        )

                        print(
                            "    Condition met:",
                            phase1_evaluation.condition_met,
                        )

                        print(
                            "    Transition:",
                            phase1_decision.transition,
                        )

                        print(
                            "    Notification required:",
                            (
                                phase1_decision
                                .should_create_notification
                            ),
                        )

                        print(
                            "    State persisted:",
                            phase1_watch_result.state_persisted,
                        )

                        print(
                            "    Reason:",
                            phase1_evaluation.reason,
                        )

                        if (
                            phase1_decision
                            .should_create_notification
                            and not notification_mode
                            .phase1_notification_execution_enabled
                        ):
                            print(
                                "    Phase 1 notification "
                                "execution: SHADOW ONLY"
                            )

                    except Exception as phase1_watch_exc:
                        phase1_failed += 1

                        print()
                        print(
                            "PHASE 1 WATCH FAILED:",
                            phase1_watch_exc,
                        )

                        if (
                            notification_mode
                            .phase0_notification_execution_enabled
                        ):
                            print(
                                "Continuing Phase 0 evaluator/"
                                "notification flow."
                            )
                        else:
                            print(
                                "Phase 0 evaluator/notification "
                                "flow is disabled. "
                                "This run will fail."
                            )

            except Exception as phase1_exc:
                phase1_failed += 1

                print()
                print(
                    "PHASE 1 PERSISTENCE FAILED:",
                    phase1_exc,
                )
                if (
                    notification_mode
                    .phase0_notification_execution_enabled
                ):
                    print(
                        "Continuing Phase 0 evaluator/"
                        "notification flow."
                    )
                else:
                    print(
                        "Phase 0 evaluator/notification "
                        "flow is disabled. "
                        "This run will fail."
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

            if (
                not notification_mode
                .phase0_notification_execution_enabled
            ):
                print()
                print(
                    "Phase 0 evaluator/notification flow: "
                    "DISABLED"
                )

                succeeded += 1
                continue

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
        "Phase 1 failures: "
        f"{phase1_failed}"
    )
    print(
        "=" * 70
    )

    if failed or phase1_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
