from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Product:
    product_id: str
    url: str
    category: str        # config key e.g. "clothes_women"
    category_path: str   # site breadcrumb e.g. "Underwear > Bras"
    name: str
    brand: str
    current_price: Optional[float]   # CZK — displayed/sale price
    original_price: Optional[float]  # CZK — crossed-out full price
    discount_pct: Optional[float]    # computed percentage
    sizes_in_stock: list = field(default_factory=list)
    colors: list = field(default_factory=list)
    sustainability_labels: list = field(default_factory=list)
    promo_tags: list = field(default_factory=list)
    image_urls: list = field(default_factory=list)
    scraped_at: str = ""

    # Labels that classify as sustainability (rest go to promo_tags)
    _SUSTAINABILITY_KEYWORDS = frozenset({
        "sustainable", "recycled", "organic", "vegan", "fair production",
        "fair trade", "fairtrade", "b corp", "bluesign", "recycled material",
        "organic cotton", "recycled polyester", "bio", "eco",
    })

    def split_labels(self, raw_labels: str) -> None:
        """Parse semicolon-delimited labels string into sustainability vs promo buckets."""
        parts = [p.strip().lower() for p in raw_labels.split(";") if p.strip()]
        for label in parts:
            if any(kw in label for kw in self._SUSTAINABILITY_KEYWORDS):
                self.sustainability_labels.append(label)
            else:
                self.promo_tags.append(label)

    def as_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "url": self.url,
            "category": self.category,
            "category_path": self.category_path,
            "name": self.name,
            "brand": self.brand,
            "current_price": self.current_price,
            "original_price": self.original_price,
            "discount_pct": self.discount_pct,
            "sizes_in_stock": "|".join(self.sizes_in_stock),
            "colors": "|".join(self.colors),
            "sustainability_labels": "|".join(self.sustainability_labels),
            "promo_tags": "|".join(self.promo_tags),
            "image_urls": "|".join(self.image_urls),
            "scraped_at": self.scraped_at,
        }

    def as_json_dict(self) -> dict:
        """Same as as_dict but with list fields kept as lists (for JSON output)."""
        d = self.as_dict()
        d["sizes_in_stock"] = self.sizes_in_stock
        d["colors"] = self.colors
        d["sustainability_labels"] = self.sustainability_labels
        d["promo_tags"] = self.promo_tags
        d["image_urls"] = self.image_urls
        return d

    CSV_HEADERS = [
        "product_id", "url", "category", "category_path", "name", "brand",
        "current_price", "original_price", "discount_pct",
        "sizes_in_stock", "colors", "sustainability_labels", "promo_tags",
        "image_urls", "scraped_at",
    ]
