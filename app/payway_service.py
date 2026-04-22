from dataclasses import dataclass

from aba_sdk import (
    PaywayAPIError,
    PaywayClient,
    PaywayConfig,
    PaywayRequestError,
)
from aba_sdk.models import Currency, PaymentOption, QRImageTemplate, QRRequest
from aba_sdk.utils.timestamp import get_req_time

from app.config import AppConfig
from app.models import PaymentResult, Product


class PaywayServiceError(Exception):
    pass


@dataclass
class PaywayService:
    config: AppConfig

    TRAN_ID_PREFIX = "ORDER-"
    MAX_TRAN_ID_LENGTH = 20

    def __post_init__(self) -> None:
        if not self.config.merchant_id or not self.config.api_key:
            raise PaywayServiceError(
                "Missing ABA credentials. Set ABA_MERCHANT_ID and ABA_API_KEY environment variables."
            )

        self._client = PaywayClient(
            PaywayConfig(
                merchant_id=self.config.merchant_id,
                api_key=self.config.api_key,
                env=self.config.environment,
            )
        )

    def generate_qr_for_product(self, product: Product) -> PaymentResult:
        tran_id = self._build_tran_id()
        request = QRRequest(
            tran_id=tran_id,
            amount=product.price_khr,
            currency=Currency.KHR,
            payment_option=PaymentOption.ABAPAY_KHQR,
            first_name="Vending",
            last_name="Machine",
            email="kiosk@example.com",
            phone="012345678",
            lifetime=self.config.qr_lifetime_minutes,
            qr_image_template=QRImageTemplate.TEMPLATE3_COLOR,
            # qr_image_template=QRImageTemplate.teme,
        )

        try:
            response = self._client.qr.generate_qr(request)
        except PaywayAPIError as error:
            raise PaywayServiceError(
                f"API Error [{error.code}]: {error.message}"
            ) from error
        except PaywayRequestError as error:
            raise PaywayServiceError(f"Network Error: {error}") from error

        status_message = "Success"
        if hasattr(response, "status") and hasattr(response.status, "message"):
            status_message = str(response.status.message)

        result_tran_id = tran_id
        if hasattr(response, "tran_id") and response.tran_id:
            result_tran_id = str(response.tran_id)

        return PaymentResult(
            tran_id=result_tran_id,
            amount_khr=product.price_khr,
            qr_string=str(response.qr_string),
            qr_image_data=getattr(response, "qr_image", None),
            status_message=status_message,
        )

    def _build_tran_id(self) -> str:
        # PayWay validates transaction id length; keep it <= 20 chars.
        req_time = get_req_time()
        base = f"{self.TRAN_ID_PREFIX}{req_time}"
        if len(base) <= self.MAX_TRAN_ID_LENGTH:
            return base

        remaining = self.MAX_TRAN_ID_LENGTH - len(self.TRAN_ID_PREFIX)
        return f"{self.TRAN_ID_PREFIX}{req_time[-remaining:]}"
