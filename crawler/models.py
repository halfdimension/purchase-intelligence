from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class ProductVariant:
    size: str
    sku: Optional[str] = None
    mrp: Optional[float] = None
    current_price: Optional[float] = None
    in_stock: Optional[bool] = None
    stock_remaining: Optional[int] = None


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
    variants: list[ProductVariant] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
