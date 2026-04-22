import json
from pathlib import Path

from app.models import Product


class ProductCatalog:
    def __init__(self, products_path: Path) -> None:
        self._products = self._load_products(products_path)

    @property
    def products(self) -> dict[str, Product]:
        return self._products

    def find_by_code(self, code: str) -> Product | None:
        return self._products.get(code)

    def _load_products(self, products_path: Path) -> dict[str, Product]:
        with products_path.open("r", encoding="utf-8") as file:
            raw_products = json.load(file)

        products: dict[str, Product] = {}
        for item in raw_products:
            code = str(item["code"]).strip()
            products[code] = Product(
                code=code,
                name=str(item["product"]).strip(),
                price_khr=int(item["price"]),
            )

        return products
