from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from crawler.models import ProductData
from crawler.scrapers.generic_jsonld import GenericJsonLdScraper


class BrowserJsonLdScraper(GenericJsonLdScraper):
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
            )

            try:
                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                if response is not None:
                    print(
                        f"Browser HTTP status: {response.status}"
                    )

                final_url = page.url

                print(
                    f"Browser final URL: {final_url}"
                )

                page.wait_for_timeout(5000)

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
