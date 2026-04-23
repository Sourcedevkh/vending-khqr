from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    price_khr: int


@dataclass(frozen=True)
class PaymentResult:
    tran_id: str
    amount_khr: int
    qr_string: str
    qr_image_data: str | None
    status_message: str
