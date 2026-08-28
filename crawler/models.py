from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class ProductData:
    url: str
    name: Optional[str] = None
    brand: Optional[str] = None
    currency: Optional[str] = None
    mrp: Optional[float] = None
    current_price: Optional[float] = None
    image_url: Optional[str] = None
    in_stock: Optional[bool] = None

    def to_dict(self):
        return asdict(self)
