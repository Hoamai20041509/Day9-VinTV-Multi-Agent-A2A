"""Delivery timeline analysis - domain logic owned by the Delivery Agent.

Owner: Delivery Agent (member 4 / specialist agent #3).

Responsibility of this module, and nothing else:

1. Compare ``order_delivered_customer_date`` with
   ``order_estimated_delivery_date`` to decide *late* vs *on time*.
2. Combine that with the Order & Seller handoff (item rows carrying
   ``seller_id`` + ``shipping_limit_date``) to split the blame between the
   seller and the logistics provider.
3. Emit the root-cause candidates ``SELLER_HANDOFF_AFTER_LIMIT``,
   ``CARRIER_DELIVERED_AFTER_ESTIMATE`` and ``DELIVERY_WITHIN_ESTIMATE``, plus
   the matching primary-issue candidate (``late_delivery_seller``,
   ``late_delivery_logistics``, ``unsupported_late_claim``).

Design rules enforced here:

* **No timezone conversion.** Timestamps are compared exactly as they appear in
  the CSV / structured input. A trailing UTC offset is dropped rather than
  shifted, so ``2018-10-18T00:00:00-03:00`` is read as the wall-clock value
  ``2018-10-18 00:00:00`` (see :func:`parse_timestamp`).
* **A missing timestamp is never a favourable fact.** "Late" requires both the
  real delivery timestamp and the estimate; "seller handed off on time"
  requires the carrier pickup timestamp. Anything else is reported as an
  incomplete timeline instead of being silently resolved.
* **No invented events.** Only fields present in the input are used; the module
  has zero I/O and zero third-party imports, so it can be unit-tested and reused
  by any agent runtime.

This module deliberately does **not** decide refunds, does not read CSV files and
does not touch payments: that is the Policy / Payment agents' scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

# --------------------------------------------------------------------------- #
# Vocabulary (mirrors EC_POLICY_V1; kept local so this module has no deps)
# --------------------------------------------------------------------------- #

CAUSE_SELLER_HANDOFF_AFTER_LIMIT = "SELLER_HANDOFF_AFTER_LIMIT"
CAUSE_CARRIER_DELIVERED_AFTER_ESTIMATE = "CARRIER_DELIVERED_AFTER_ESTIMATE"
CAUSE_DELIVERY_WITHIN_ESTIMATE = "DELIVERY_WITHIN_ESTIMATE"

ISSUE_LATE_DELIVERY_SELLER = "late_delivery_seller"
ISSUE_LATE_DELIVERY_LOGISTICS = "late_delivery_logistics"
ISSUE_UNSUPPORTED_LATE_CLAIM = "unsupported_late_claim"

PARTY_SELLER = "seller"
PARTY_LOGISTICS = "logistics_provider"
LOGISTICS_PARTY_ID = "LOGISTICS_PROVIDER"

VERDICT_LATE = "late"
VERDICT_ON_TIME = "on_time"
VERDICT_NOT_DELIVERED = "not_delivered"
VERDICT_UNKNOWN = "unknown"

SECONDS_PER_DAY = 86400.0

# Deterministic confidence for the delivery domain: it encodes how completely the
# timestamps pin the verdict down, not a sampling score.
CONFIDENCE_LATE_SELLER = 0.93
CONFIDENCE_LATE_LOGISTICS = 0.91
CONFIDENCE_ON_TIME = 0.89
CONFIDENCE_UNKNOWN = 0.4
PENALTY_MISSING_HANDOFF = 0.08
PENALTY_NO_ITEMS = 0.05
CONFIDENCE_FLOOR = 0.30
CONFIDENCE_CEILING = 0.97

MAX_ITEM_EVIDENCE = 3
MAX_SELLER_EVIDENCE = 2

_TZ_SUFFIX_RE = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")
_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
)
_NULL_TOKENS = frozenset({"", "nan", "nat", "none", "null", "na", "-"})

# Aliases accepted for each timeline field, so the agent tolerates both raw CSV
# column names and shortened keys coming from another agent's payload.
_ORDER_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "order_id": ("order_id", "claimed_order_id", "id"),
    "order_status": ("order_status", "status"),
    "order_purchase_timestamp": ("order_purchase_timestamp", "purchase_timestamp"),
    "order_approved_at": ("order_approved_at", "approved_at"),
    "order_delivered_carrier_date": (
        "order_delivered_carrier_date",
        "delivered_carrier_date",
        "carrier_date",
    ),
    "order_delivered_customer_date": (
        "order_delivered_customer_date",
        "delivered_customer_date",
        "customer_date",
    ),
    "order_estimated_delivery_date": (
        "order_estimated_delivery_date",
        "estimated_delivery_date",
        "estimated_date",
    ),
}

_ITEM_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "order_id": ("order_id",),
    "order_item_id": ("order_item_id", "item_id", "sequential"),
    "seller_id": ("seller_id", "seller"),
    "shipping_limit_date": ("shipping_limit_date", "shipping_limit"),
}


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #


def parse_timestamp(value: Any) -> datetime | None:
    """Parse an Olist timestamp **without any timezone conversion**.

    The lab spec says timestamps are compared by their CSV value, so a UTC
    offset is stripped instead of being applied: the wall-clock reading is kept
    verbatim and the result is always naive. Empty strings and the various NaN
    spellings that pandas emits map to ``None`` rather than to a fake date.

    >>> parse_timestamp("2018-10-18T00:00:00-03:00").isoformat()
    '2018-10-18T00:00:00'
    >>> parse_timestamp("nan") is None
    True
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip()
    if text.lower() in _NULL_TOKENS:
        return None
    text = _TZ_SUFFIX_RE.sub("", text).strip()
    if "." in text:
        text = text.split(".", 1)[0]
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def as_mapping(value: Any) -> Mapping[str, Any] | None:
    """Coerce a record-like object into a plain mapping.

    Accepts a ``dict``/``Mapping`` as-is and also tolerates objects exposing
    ``to_dict()`` (notably ``pandas.Series``, which upstream agents get for free
    when they read the CSVs). Anything else becomes ``None`` so the caller can
    report missing input instead of crashing.
    """
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            converted = to_dict()
        except Exception:
            return None
        if isinstance(converted, Mapping):
            return converted
    return None


def _pick(source: Mapping[str, Any], aliases: Iterable[str]) -> Any:
    for alias in aliases:
        if alias in source and source[alias] is not None:
            return source[alias]
    return None


def _clean_id(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in _NULL_TOKENS else text


def _delta_days(later: datetime, earlier: datetime) -> float:
    """Signed difference in days between two naive timestamps."""
    return round((later - earlier).total_seconds() / SECONDS_PER_DAY, 3)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat(sep=" ")


# --------------------------------------------------------------------------- #
# Normalised input structures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DeliveryTimeline:
    """The order-level timestamps the delivery verdict depends on."""

    order_id: str = ""
    order_status: str = ""
    purchase_timestamp: datetime | None = None
    approved_at: datetime | None = None
    delivered_carrier_date: datetime | None = None
    delivered_customer_date: datetime | None = None
    estimated_delivery_date: datetime | None = None

    @classmethod
    def from_mapping(cls, payload: Any = None) -> "DeliveryTimeline":
        payload = as_mapping(payload) or {}
        return cls(
            order_id=_clean_id(_pick(payload, _ORDER_FIELD_ALIASES["order_id"])),
            order_status=_clean_id(
                _pick(payload, _ORDER_FIELD_ALIASES["order_status"])
            ).lower(),
            purchase_timestamp=parse_timestamp(
                _pick(payload, _ORDER_FIELD_ALIASES["order_purchase_timestamp"])
            ),
            approved_at=parse_timestamp(
                _pick(payload, _ORDER_FIELD_ALIASES["order_approved_at"])
            ),
            delivered_carrier_date=parse_timestamp(
                _pick(payload, _ORDER_FIELD_ALIASES["order_delivered_carrier_date"])
            ),
            delivered_customer_date=parse_timestamp(
                _pick(payload, _ORDER_FIELD_ALIASES["order_delivered_customer_date"])
            ),
            estimated_delivery_date=parse_timestamp(
                _pick(payload, _ORDER_FIELD_ALIASES["order_estimated_delivery_date"])
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "order_status": self.order_status,
            "order_purchase_timestamp": _iso(self.purchase_timestamp),
            "order_approved_at": _iso(self.approved_at),
            "order_delivered_carrier_date": _iso(self.delivered_carrier_date),
            "order_delivered_customer_date": _iso(self.delivered_customer_date),
            "order_estimated_delivery_date": _iso(self.estimated_delivery_date),
        }


@dataclass(frozen=True)
class ShipmentItem:
    """One item row: the seller and the deadline that seller had to meet."""

    order_id: str = ""
    order_item_id: str = ""
    seller_id: str = ""
    shipping_limit_date: datetime | None = None

    @classmethod
    def from_mapping(
        cls, payload: Any = None, fallback_order_id: str = ""
    ) -> "ShipmentItem":
        payload = as_mapping(payload) or {}
        order_id = _clean_id(_pick(payload, _ITEM_FIELD_ALIASES["order_id"]))
        return cls(
            order_id=order_id or fallback_order_id,
            order_item_id=_clean_id(
                _pick(payload, _ITEM_FIELD_ALIASES["order_item_id"])
            ),
            seller_id=_clean_id(_pick(payload, _ITEM_FIELD_ALIASES["seller_id"])),
            shipping_limit_date=parse_timestamp(
                _pick(payload, _ITEM_FIELD_ALIASES["shipping_limit_date"])
            ),
        )

    @property
    def item_key(self) -> str:
        return f"{self.order_id}:{self.order_item_id}"


def normalize_items(
    rows: Sequence[Any] | None, fallback_order_id: str = ""
) -> tuple[ShipmentItem, ...]:
    """Convert raw item payloads into :class:`ShipmentItem` records.

    Rows that cannot be interpreted as records are skipped rather than guessed at.
    """
    if not rows:
        return ()
    records: list[ShipmentItem] = []
    for row in rows:
        mapping = as_mapping(row)
        if mapping is None:
            continue
        records.append(
            ShipmentItem.from_mapping(mapping, fallback_order_id=fallback_order_id)
        )
    return tuple(records)


# --------------------------------------------------------------------------- #
# Core rules
# --------------------------------------------------------------------------- #


def is_delivered_late(
    delivered_customer_date: datetime | None,
    estimated_delivery_date: datetime | None,
) -> bool:
    """``True`` only when a real delivery timestamp is strictly after the estimate.

    Returns ``False`` when either timestamp is missing: an order without a
    delivery timestamp is not proof of a late delivery (it is usually a
    canceled / unavailable order, which another rule owns).
    """
    if delivered_customer_date is None or estimated_delivery_date is None:
        return False
    return delivered_customer_date > estimated_delivery_date


def delivery_delay_days(
    delivered_customer_date: datetime | None,
    estimated_delivery_date: datetime | None,
) -> float | None:
    """Signed days between actual delivery and the estimate (negative = early)."""
    if delivered_customer_date is None or estimated_delivery_date is None:
        return None
    return _delta_days(delivered_customer_date, estimated_delivery_date)


def late_seller_ids(
    items: Sequence[ShipmentItem],
    delivered_carrier_date: datetime | None,
) -> tuple[str, ...]:
    """Sellers that missed their ``shipping_limit_date`` at carrier handoff.

    Per the README convention for multi-item orders, a seller is flagged when
    ``order_delivered_carrier_date > shipping_limit_date`` for at least one of
    that seller's item rows. Input order is preserved so the resulting evidence
    is reproducible.
    """
    if delivered_carrier_date is None:
        return ()
    flagged: list[str] = []
    for item in items:
        if not item.seller_id or item.shipping_limit_date is None:
            continue
        if delivered_carrier_date > item.shipping_limit_date:
            if item.seller_id not in flagged:
                flagged.append(item.seller_id)
    return tuple(flagged)


def worst_handoff_delay_days(
    items: Sequence[ShipmentItem],
    delivered_carrier_date: datetime | None,
) -> float | None:
    """Largest positive handoff overrun in days, or ``None`` when no limit was missed."""
    if delivered_carrier_date is None:
        return None
    delays = [
        _delta_days(delivered_carrier_date, item.shipping_limit_date)
        for item in items
        if item.shipping_limit_date is not None
        and delivered_carrier_date > item.shipping_limit_date
    ]
    return max(delays) if delays else None


def rank_delivery_causes(
    late_vs_estimate: bool,
    seller_handoff_late: bool,
    timeline_complete: bool,
) -> tuple[str, ...]:
    """Ordered root-cause candidates for the delivery domain (rank 1 first).

    * late + seller missed the handoff limit ->
      ``SELLER_HANDOFF_AFTER_LIMIT`` then ``CARRIER_DELIVERED_AFTER_ESTIMATE``
      (the seller is the root cause, the late arrival is the effect).
    * late + seller handed off on time -> ``CARRIER_DELIVERED_AFTER_ESTIMATE``.
    * delivered no later than the estimate -> ``DELIVERY_WITHIN_ESTIMATE``.
    * timeline not evaluable -> no candidate; another domain owns the case.
    """
    if late_vs_estimate:
        if seller_handoff_late:
            return (
                CAUSE_SELLER_HANDOFF_AFTER_LIMIT,
                CAUSE_CARRIER_DELIVERED_AFTER_ESTIMATE,
            )
        return (CAUSE_CARRIER_DELIVERED_AFTER_ESTIMATE,)
    if timeline_complete:
        return (CAUSE_DELIVERY_WITHIN_ESTIMATE,)
    return ()


def _clamp_confidence(value: float) -> float:
    return round(min(CONFIDENCE_CEILING, max(CONFIDENCE_FLOOR, value)), 2)


# --------------------------------------------------------------------------- #
# Finding (structured output of the delivery domain)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DeliveryFinding:
    """Structured verdict handed off to the Policy / Verifier agents."""

    order_id: str
    timeline: DeliveryTimeline
    delivered: bool
    handed_to_carrier: bool
    timeline_complete: bool
    delivery_verdict: str
    late_vs_estimate: bool
    delay_days: float | None
    seller_handoff_late: bool
    late_seller_ids: tuple[str, ...]
    handoff_delay_days: float | None
    cause_candidates: tuple[str, ...]
    issue_candidate: str | None
    responsible_parties: tuple[tuple[str, str], ...]
    confidence: float
    evidence_ids: tuple[str, ...]
    notes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_actionable(self) -> bool:
        """True when the delivery domain found a late delivery to compensate."""
        return self.late_vs_estimate

    @property
    def has_usable_timeline(self) -> bool:
        return self.delivery_verdict in (VERDICT_LATE, VERDICT_ON_TIME)

    def ranked_causes(self) -> list[dict[str, Any]]:
        return [
            {"cause_code": code, "rank": index + 1}
            for index, code in enumerate(self.cause_candidates)
        ]

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection used as the ``result`` block of the A2A envelope."""
        return {
            "order_id": self.order_id,
            "delivery_verdict": self.delivery_verdict,
            "late_vs_estimate": self.late_vs_estimate,
            "delay_days": self.delay_days,
            "delivered": self.delivered,
            "handed_to_carrier": self.handed_to_carrier,
            "timeline_complete": self.timeline_complete,
            "seller_handoff_late": self.seller_handoff_late,
            "late_seller_ids": list(self.late_seller_ids),
            "handoff_delay_days": self.handoff_delay_days,
            "cause_candidates": list(self.cause_candidates),
            "ranked_causes": self.ranked_causes(),
            "issue_candidate": self.issue_candidate,
            "responsible_parties": [
                {"party_type": party_type, "party_id": party_id}
                for party_type, party_id in self.responsible_parties
            ],
            "confidence": self.confidence,
            "evidence_ids": list(self.evidence_ids),
            "timeline": self.timeline.to_dict(),
            "notes": list(self.notes),
            "warnings": list(self.warnings),
        }

    def summary(self) -> str:
        """One-line human summary for the ``summary`` field of the envelope."""
        if self.delivery_verdict == VERDICT_LATE:
            delay = f"{self.delay_days:+.2f}d" if self.delay_days is not None else "?"
            if self.seller_handoff_late:
                sellers = ", ".join(self.late_seller_ids) or "unknown seller"
                return (
                    f"Giao tre {delay} so voi han cam ket; seller ban giao qua "
                    f"shipping_limit_date ({sellers}) -> {ISSUE_LATE_DELIVERY_SELLER}."
                )
            return (
                f"Giao tre {delay} so voi han cam ket; seller ban giao dung han "
                f"-> {ISSUE_LATE_DELIVERY_LOGISTICS}."
            )
        if self.delivery_verdict == VERDICT_ON_TIME:
            delay = f"{self.delay_days:+.2f}d" if self.delay_days is not None else "?"
            return (
                f"Giao dung/som han cam ket ({delay}); khong co can cu giao tre "
                f"-> {ISSUE_UNSUPPORTED_LATE_CLAIM}."
            )
        if self.delivery_verdict == VERDICT_NOT_DELIVERED:
            return (
                f"Khong co order_delivered_customer_date (status="
                f"{self.timeline.order_status or 'unknown'}); khong ket luan giao tre."
            )
        return "Khong du timestamp de danh gia moc giao hang."


def _build_evidence(
    timeline: DeliveryTimeline,
    items: Sequence[ShipmentItem],
    flagged_sellers: Sequence[str],
    causes: Sequence[str],
) -> tuple[str, ...]:
    """Evidence IDs the delivery domain can prove from its own input rows."""
    evidence: list[str] = []

    def add(candidate: str) -> None:
        if candidate not in evidence:
            evidence.append(candidate)

    if timeline.order_id:
        add(f"order:{timeline.order_id}")
    # Cite the item rows that carry the missed deadlines first.
    ordered_items = sorted(
        items,
        key=lambda item: (item.seller_id not in set(flagged_sellers), item.item_key),
    )
    for item in ordered_items[:MAX_ITEM_EVIDENCE]:
        if item.order_id and item.order_item_id:
            add(f"item:{item.item_key}")
    for seller_id in list(flagged_sellers)[:MAX_SELLER_EVIDENCE]:
        add(f"seller:{seller_id}")
    for cause in causes:
        add(f"policy:{cause}")
    return tuple(evidence)


def analyze_delivery(
    order: Mapping[str, Any] | DeliveryTimeline | Any | None,
    items: Sequence[Any] | None = None,
) -> DeliveryFinding:
    """Turn an order timeline plus its item rows into a :class:`DeliveryFinding`.

    ``order`` accepts a raw CSV-shaped mapping, a shortened mapping from another
    agent, or an already normalised :class:`DeliveryTimeline`. ``items`` accepts
    the same flexibility. Missing input degrades gracefully: the verdict becomes
    ``unknown`` / ``not_delivered`` with an explanatory warning instead of an
    exception or a fabricated conclusion.
    """
    if isinstance(order, DeliveryTimeline):
        timeline = order
    else:
        timeline = DeliveryTimeline.from_mapping(order)

    if items and all(isinstance(row, ShipmentItem) for row in items):
        shipment_items: tuple[ShipmentItem, ...] = tuple(items)  # type: ignore[arg-type]
    else:
        shipment_items = normalize_items(items, fallback_order_id=timeline.order_id)

    notes: list[str] = []
    warnings: list[str] = []

    order_missing = order is None or (
        timeline.delivered_customer_date is None
        and timeline.estimated_delivery_date is None
        and timeline.delivered_carrier_date is None
        and not timeline.order_status
    )

    delivered = timeline.delivered_customer_date is not None
    handed_to_carrier = timeline.delivered_carrier_date is not None
    timeline_complete = delivered and timeline.estimated_delivery_date is not None

    late = is_delivered_late(
        timeline.delivered_customer_date, timeline.estimated_delivery_date
    )
    delay = delivery_delay_days(
        timeline.delivered_customer_date, timeline.estimated_delivery_date
    )

    flagged_sellers = late_seller_ids(shipment_items, timeline.delivered_carrier_date)
    seller_handoff_late = bool(flagged_sellers)
    handoff_delay = worst_handoff_delay_days(
        shipment_items, timeline.delivered_carrier_date
    )

    # ---------------------------------------------------------------- verdict
    if order_missing:
        verdict = VERDICT_UNKNOWN
        warnings.append("khong nhan duoc du lieu order: khong the danh gia moc giao")
    elif timeline_complete:
        verdict = VERDICT_LATE if late else VERDICT_ON_TIME
    elif delivered:
        verdict = VERDICT_UNKNOWN
        warnings.append(
            "thieu order_estimated_delivery_date: khong so sanh duoc han cam ket"
        )
    else:
        verdict = VERDICT_NOT_DELIVERED
        notes.append(
            "thieu order_delivered_customer_date (status="
            f"{timeline.order_status or 'unknown'}): khong ket luan giao tre"
        )

    causes = rank_delivery_causes(late, seller_handoff_late, timeline_complete)

    # ------------------------------------------------- issue + responsibility
    issue_candidate: str | None
    responsible: tuple[tuple[str, str], ...]
    confidence: float

    if verdict == VERDICT_LATE and seller_handoff_late:
        issue_candidate = ISSUE_LATE_DELIVERY_SELLER
        responsible = tuple((PARTY_SELLER, seller_id) for seller_id in flagged_sellers)
        confidence = CONFIDENCE_LATE_SELLER
        notes.append(
            "order_delivered_carrier_date sau shipping_limit_date cua seller: "
            + ", ".join(flagged_sellers)
        )
    elif verdict == VERDICT_LATE:
        issue_candidate = ISSUE_LATE_DELIVERY_LOGISTICS
        responsible = ((PARTY_LOGISTICS, LOGISTICS_PARTY_ID),)
        confidence = CONFIDENCE_LATE_LOGISTICS
        if not handed_to_carrier:
            confidence -= PENALTY_MISSING_HANDOFF
            warnings.append(
                "thieu order_delivered_carrier_date: khong chung minh duoc seller "
                "ban giao tre nen quy trach nhiem cho logistics theo quy tac "
                "'khong muon hon shipping_limit_date'"
            )
        elif not shipment_items:
            confidence -= PENALTY_NO_ITEMS
            warnings.append(
                "khong co item row: khong doi chieu duoc shipping_limit_date"
            )
        else:
            notes.append(
                "order_delivered_carrier_date khong muon hon moi shipping_limit_date"
            )
    elif verdict == VERDICT_ON_TIME:
        issue_candidate = ISSUE_UNSUPPORTED_LATE_CLAIM
        responsible = ()
        confidence = CONFIDENCE_ON_TIME
        notes.append(
            "order_delivered_customer_date khong muon hon order_estimated_delivery_date"
        )
    else:
        issue_candidate = None
        responsible = ()
        confidence = CONFIDENCE_UNKNOWN
        notes.append(
            "khong de xuat primary_issue tu domain delivery; nhuong cho rule "
            "canceled/unavailable hoac payment"
        )

    if seller_handoff_late and verdict != VERDICT_LATE:
        notes.append(
            "seller ban giao qua shipping_limit_date nhung don khong tre so voi "
            "han cam ket: khong du can cu de quy trach nhiem seller"
        )

    return DeliveryFinding(
        order_id=timeline.order_id,
        timeline=timeline,
        delivered=delivered,
        handed_to_carrier=handed_to_carrier,
        timeline_complete=timeline_complete,
        delivery_verdict=verdict,
        late_vs_estimate=late,
        delay_days=delay,
        seller_handoff_late=seller_handoff_late,
        late_seller_ids=flagged_sellers,
        handoff_delay_days=handoff_delay,
        cause_candidates=causes,
        issue_candidate=issue_candidate,
        responsible_parties=responsible,
        confidence=_clamp_confidence(confidence),
        evidence_ids=_build_evidence(
            timeline, shipment_items, flagged_sellers, causes
        ),
        notes=tuple(notes),
        warnings=tuple(warnings),
    )