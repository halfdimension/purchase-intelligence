from bs4 import BeautifulSoup
from playwright.sync_api import (
    Error as PlaywrightError,
    sync_playwright,
)

from crawler.models import ProductData
from crawler.scrapers.generic_jsonld import GenericJsonLdScraper


class UnsafeMainFrameNavigationError(RuntimeError):
    pass


class GuardedMainFrameHttpError(RuntimeError):
    pass


def _main_frame_document_url(
    event: dict,
    main_frame_id: str,
) -> str | None:
    if (
        event.get("resourceType") != "Document"
        or event.get("frameId") != main_frame_id
    ):
        return None

    request = event.get("request")

    if not isinstance(request, dict):
        raise RuntimeError(
            "Browser request interception omitted request data."
        )

    url = request.get("url")

    if not isinstance(url, str):
        raise RuntimeError(
            "Browser request interception omitted the request URL."
        )

    return url


class BrowserJsonLdScraper(GenericJsonLdScraper):
    guard_main_frame_navigations = False

    def validate_main_frame_navigation(
        self,
        url: str,
    ) -> None:
        """
        Optional retailer-specific top-level navigation guard.

        Subclasses may reject a main-frame URL. Subresources are
        intentionally outside this hook.
        """

        return None

    def validate_main_frame_response_status(
        self,
        status: int,
    ) -> None:
        if (
            self.guard_main_frame_navigations
            and status >= 400
        ):
            raise GuardedMainFrameHttpError(
                "Guarded retailer page returned HTTP "
                f"status {status}."
            )

    def fetch_rendered_html(
        self,
        url: str,
    ) -> tuple[str, str]:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
            )

            page = browser.new_page(
                locale="en-IN",
                service_workers=(
                    "block"
                    if self.guard_main_frame_navigations
                    else "allow"
                ),
            )

            blocked_navigation: ValueError | None = None

            def validated_main_frame_url() -> str:
                if blocked_navigation is not None:
                    raise UnsafeMainFrameNavigationError(
                        "Retailer navigation left its allowed hostname."
                    ) from blocked_navigation

                current_url = page.url

                if self.guard_main_frame_navigations:
                    try:
                        self.validate_main_frame_navigation(
                            current_url
                        )
                    except ValueError as exc:
                        raise UnsafeMainFrameNavigationError(
                            "Retailer navigation left its allowed hostname."
                        ) from exc

                return current_url

            if self.guard_main_frame_navigations:
                cdp_session = (
                    page.context.new_cdp_session(
                        page
                    )
                )
                frame_tree = cdp_session.send(
                    "Page.getFrameTree"
                )
                main_frame_id = frame_tree[
                    "frameTree"
                ]["frame"]["id"]

                def guard_paused_request(
                    event: dict,
                ) -> None:
                    nonlocal blocked_navigation

                    navigation_url = (
                        _main_frame_document_url(
                            event,
                            main_frame_id,
                        )
                    )

                    if navigation_url is not None:
                        try:
                            self.validate_main_frame_navigation(
                                navigation_url
                            )
                        except ValueError as exc:
                            blocked_navigation = exc
                            cdp_session.send(
                                "Fetch.failRequest",
                                {
                                    "requestId": event[
                                        "requestId"
                                    ],
                                    "errorReason": (
                                        "BlockedByClient"
                                    ),
                                },
                            )
                            return

                    cdp_session.send(
                        "Fetch.continueRequest",
                        {
                            "requestId": event[
                                "requestId"
                            ],
                        },
                    )

                cdp_session.on(
                    "Fetch.requestPaused",
                    guard_paused_request,
                )
                cdp_session.send(
                    "Fetch.enable",
                    {
                        "patterns": [
                            {
                                "urlPattern": "*",
                                "requestStage": (
                                    "Request"
                                ),
                            }
                        ]
                    },
                )

            try:
                try:
                    response = page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                except PlaywrightError:
                    if blocked_navigation is None:
                        raise

                    raise UnsafeMainFrameNavigationError(
                        "Retailer navigation left its allowed hostname."
                    ) from blocked_navigation

                if response is not None:
                    print(
                        f"Browser HTTP status: {response.status}"
                    )
                    self.validate_main_frame_response_status(
                        response.status
                    )

                final_url = validated_main_frame_url()

                print(
                    f"Browser final URL: {final_url}"
                )

                page.wait_for_timeout(5000)

                final_url = validated_main_frame_url()

                html = page.content()

                print(
                    f"Browser HTML: {len(html)} bytes"
                )

                return final_url, html

            finally:
                browser.close()

    def scrape(self, url: str) -> ProductData:
        final_url, html = self.fetch_rendered_html(url)

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        product = self._find_product_json_ld(
            soup
        )

        if product:
            print(
                "Structured Product JSON-LD "
                "found through browser."
            )

            return self._from_json_ld(
                final_url,
                product,
            )

        print(
            "No Product JSON-LD found through browser. "
            "Trying HTML metadata fallback."
        )

        return self._from_metadata(
            final_url,
            soup,
        )
