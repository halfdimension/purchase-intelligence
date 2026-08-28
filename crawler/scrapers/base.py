from abc import ABC, abstractmethod

from crawler.models import ProductData


class BaseScraper(ABC):
    @abstractmethod
    def scrape(self, url: str) -> ProductData:
        pass
