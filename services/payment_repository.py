
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from services.data_loader import DATA_DIR, read_csv_rows
from shared.schemas import PaymentRow


PAYMENTS_CSV = DATA_DIR / "olist_order_payments_dataset.csv"


def money_to_decimal(value: str | int | float | Decimal) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid BRL money value: {value!r}") from exc


def money_to_float(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class PaymentRepository:
    def __init__(self, csv_path: str | Path = PAYMENTS_CSV) -> None:
        self.csv_path = Path(csv_path)
        self._rows_by_order_id: dict[str, list[PaymentRow]] | None = None

    def get_by_order_id(self, order_id: str) -> list[PaymentRow]:
        if self._rows_by_order_id is None:
            self._load()
        return list(self._rows_by_order_id.get(order_id, []))

    def _load(self) -> None:
        rows_by_order_id: dict[str, list[PaymentRow]] = {}
        for row in read_csv_rows(self.csv_path):
            payment = PaymentRow(
                order_id=row["order_id"],
                payment_sequential=int(row["payment_sequential"]),
                payment_type=row["payment_type"],
                payment_installments=int(row["payment_installments"]),
                payment_value_brl=money_to_float(money_to_decimal(row["payment_value"])),
            )
            rows_by_order_id.setdefault(payment.order_id, []).append(payment)

        for payments in rows_by_order_id.values():
            payments.sort(key=lambda item: item.payment_sequential)

        self._rows_by_order_id = rows_by_order_id
