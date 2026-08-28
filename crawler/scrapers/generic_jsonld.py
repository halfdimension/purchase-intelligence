import json
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from crawler.models import ProductData
from crawler.scrapers.base import BaseScraper


class GenericJsonLdScraper(BaseScraper):
    def __init__(self):
        self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-IN,en;q=0.9",
            }
        )

    def scrape(self, url: str) -> ProductData:
        response = self.session.get(
            url,
            timeout=30,
            allow_redirects=True,
        )

        print(f"HTTP status: {response.status_code}")
        print(f"Final URL: {response.url}")
        print(f"Downloaded: {len(response.content)} bytes")

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        product = self._find_product_json_ld(soup)

        if product:
            print("Structured Product JSON-LD found.")
            return self._from_json_ld(response.url, product)

        print("No Product JSON-LD found. Trying HTML metadata fallback.")

        return self._from_metadata(response.url, soup)

    def _find_product_json_ld(
        self,
        soup: BeautifulSoup,
    ) -> Optional[dict[str, Any]]:
        scripts = soup.find_all(
            "script",
            attrs={"type": "application/ld+json"},
        )

        print(f"JSON-LD blocks found: {len(scripts)}")

        for script in scripts:
            if not script.string:
                continue

            try:
                payload = json.loads(script.string)
            except json.JSONDecodeError:
                continue

            product = self._find_product(payload)

            if product is not None:
                return product

        return None

    def _find_product(
        self,
        value: Any,
    ) -> Optional[dict[str, Any]]:
        if isinstance(value, dict):
            object_type = value.get("@type")

            if object_type == "Product":
                return value

            if (
                isinstance(object_type, list)
                and "Product" in object_type
            ):
                return value

            for child in value.values():
                result = self._find_product(child)

                if result is not None:
                    return result

        elif isinstance(value, list):
            for child in value:
                result = self._find_product(child)

                if result is not None:
                    return result

        return None

    def _from_json_ld(
        self,
        url: str,
        product: dict[str, Any],
    ) -> ProductData:
        offers = product.get("offers")

        if isinstance(offers, list):
            offer = offers[0] if offers else {}
        elif isinstance(offers, dict):
            offer = offers
        else:
            offer = {}

        price = self._to_float(
            offer.get("price")
            or offer.get("lowPrice")
        )

        currency = offer.get("priceCurrency")

        availability = offer.get("availability")

        in_stock = self._parse_availability(
            availability
        )

        brand = product.get("brand")

        if isinstance(brand, dict):
            brand = brand.get("name")

        image = product.get("image")

        if isinstance(image, list):
            image = image[0] if image else None

        elif isinstance(image, dict):
            image = (
                image.get("url")
                or image.get("contentUrl")
            )

        return ProductData(
            url=url,
            name=product.get("name"),
            brand=self._normalize_brand(url, brand),
            currency=currency,
            current_price=price,
            image_url=image,
            in_stock=in_stock,
        )

    def _from_metadata(
        self,
        url: str,
        soup: BeautifulSoup,
    ) -> ProductData:
        title = self._meta_content(
            soup,
            property_name="og:title",
        )

        image = self._meta_content(
            soup,
            property_name="og:image",
        )

        price = (
            self._meta_content(
                soup,
                property_name="product:price:amount",
            )
            or self._meta_content(
                soup,
                property_name="og:price:amount",
            )
        )

        currency = (
            self._meta_content(
                soup,
                property_name="product:price:currency",
            )
            or self._meta_content(
                soup,
                property_name="og:price:currency",
            )
        )

        return ProductData(
            url=url,
            name=title,
            currency=currency,
            current_price=self._to_float(price),
            image_url=image,
        )

    def _meta_content(
        self,
        soup: BeautifulSoup,
        property_name: str,
    ) -> Optional[str]:
        tag = soup.find(
            "meta",
            attrs={"property": property_name},
        )

        if tag is None:
            return None

        content = tag.get("content")

        if isinstance(content, str):
            return content.strip()

        return None

    def _normalize_brand(
        self,
        url: str,
        raw_brand: Any,
    ) -> Optional[str]:
        hostname = (
            urlparse(url).hostname or ""
        ).lower()

        if "nike." in hostname:
            return "Nike"

        if "adidas." in hostname:
            return "Adidas"

        if "asics." in hostname:
            return "ASICS"

        if isinstance(raw_brand, str):
            value = raw_brand.strip()

            if value:
                return value

        return None

    def _parse_availability(
        self,
        availability: Any,
    ) -> Optional[bool]:
        if not isinstance(availability, str):
            return None

        value = availability.lower()

        if "instock" in value:
            return True

        if (
            "outofstock" in value
            or "soldout" in value
        ):
            return False

        return None

    def _to_float(
        self,
        value: Any,
    ) -> Optional[float]:
        if value is None:
            return None

        try:
            cleaned = (
                str(value)
                .replace(",", "")
                .replace("₹", "")
                .strip()
            )

            return float(cleaned)

        except (TypeError, ValueError):
            return None
