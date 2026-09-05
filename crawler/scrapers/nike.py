import json
import re
from typing import Any, Optional

from bs4 import BeautifulSoup

from crawler.models import ProductData, ProductVariant
from crawler.scrapers.browser_jsonld import BrowserJsonLdScraper
from crawler.scrapers.nike_url import (
    require_nike_india_hostname,
)


class NikeScraper(BrowserJsonLdScraper):
    def __init__(
        self,
        *,
        guard_main_frame_navigations: bool = False,
    ) -> None:
        self.guard_main_frame_navigations = (
            guard_main_frame_navigations
        )

    def validate_main_frame_navigation(
        self,
        url: str,
    ) -> None:
        require_nike_india_hostname(url)

    def scrape(self, url: str) -> ProductData:
        final_url, html = self.fetch_rendered_html(url)

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        json_ld = self._find_product_json_ld(
            soup
        )

        if json_ld:
            print(
                "Nike: Product JSON-LD found."
            )

            product = self._from_json_ld(
                final_url,
                json_ld,
            )
        else:
            print(
                "Nike: JSON-LD missing, using metadata."
            )

            product = self._from_metadata(
                final_url,
                soup,
            )

        product.brand = "Nike"

        product_state = self._extract_product_state(
            html
        )

        if product_state:
            mrp = self._to_float(
                product_state.get("price")
            )

            current_price = self._to_float(
                product_state.get("discountedPrice")
            )

            if mrp is not None:
                product.mrp = mrp

            if current_price is not None:
                product.current_price = current_price

            if not product.image_url:
                image_url = product_state.get(
                    "imageUrl"
                )

                if isinstance(image_url, str):
                    product.image_url = image_url

        options = self._extract_size_options(
            html
        )

        product.variants = [
            self._variant_from_option(option)
            for option in options
            if isinstance(option, dict)
            and isinstance(option.get("sizeName"), str)
        ]

        if product.variants:
            product.in_stock = any(
                variant.in_stock is True
                for variant in product.variants
            )

        print(
            f"Nike variants extracted: "
            f"{len(product.variants)}"
        )

        return product

    def _extract_product_state(
        self,
        html: str,
    ) -> Optional[dict[str, Any]]:
        pattern = re.compile(
            r'"skuData"\s*:\s*\{\s*"product"\s*:'
        )

        match = pattern.search(html)

        if match is None:
            return None

        start = html.find(
            "{",
            match.end(),
        )

        if start == -1:
            return None

        decoder = json.JSONDecoder()

        try:
            value, _ = decoder.raw_decode(
                html[start:]
            )
        except json.JSONDecodeError:
            return None

        if isinstance(value, dict):
            return value

        return None

    def _extract_size_options(
        self,
        html: str,
    ) -> list[dict[str, Any]]:
        decoder = json.JSONDecoder()

        matches = re.finditer(
            r'"sizeOptions"\s*:',
            html,
        )

        for match in matches:
            start = html.find(
                "{",
                match.end(),
            )

            if start == -1:
                continue

            try:
                value, _ = decoder.raw_decode(
                    html[start:]
                )
            except json.JSONDecodeError:
                continue

            if not isinstance(value, dict):
                continue

            options = value.get("options")

            if (
                isinstance(options, list)
                and options
            ):
                return [
                    option
                    for option in options
                    if isinstance(option, dict)
                ]

        return []

    def _variant_from_option(
        self,
        option: dict[str, Any],
    ) -> ProductVariant:
        out_of_stock = option.get(
            "isOutOfStock"
        )

        if out_of_stock == 1:
            in_stock = False
        elif out_of_stock == 0:
            in_stock = True
        else:
            in_stock = None

        stock_remaining = option.get(
            "stock_remaining"
        )

        if not isinstance(stock_remaining, int):
            stock_remaining = None

        return ProductVariant(
            size=option["sizeName"],
            sku=option.get("sku"),
            mrp=self._to_float(
                option.get("price")
            ),
            current_price=self._to_float(
                option.get("discountedPrice")
            ),
            in_stock=in_stock,
            stock_remaining=stock_remaining,
        )
