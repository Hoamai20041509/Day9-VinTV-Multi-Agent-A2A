"""Application-wide constants that must be visible during grading."""

MODEL_NAME = "Qwen/Qwen3-8B"
MODEL_PARAMETER_SIZE_BILLION = 8.2
MODEL_FRAMEWORK = "transformers"
MODEL_RUNTIME = "local"

# Order investigation is a short structured task, so non-thinking mode keeps
# inference cost and unstructured output small.
MODEL_ENABLE_THINKING = False
MODEL_MAX_NEW_TOKENS = 512
MODEL_TEMPERATURE = 0.7
MODEL_TOP_P = 0.8
MODEL_TOP_K = 20

POLICY_VERSION = "EC_POLICY_V1"
CURRENCY = "BRL"
PAYMENT_TOLERANCE_BRL = 0.10
MAX_ENTITY_IDS = 5
MAX_EVIDENCE_IDS = 10
MAX_ROOT_CAUSES = 3
MAX_RESPONSIBLE_PARTIES = 3
MAX_ACTIONS = 5

ISSUE_RULES = {
    "canceled_order_paid": {
        "cause": "ORDER_CANCELED_AFTER_PAYMENT",
        "party_type": "platform",
        "party_id": "OLIST_PLATFORM",
        "action": "issue_full_refund",
        "confidence": 1.0,
    },
    "unavailable_order_paid": {
        "cause": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
        "party_type": "platform",
        "party_id": "OLIST_PLATFORM",
        "action": "issue_full_refund",
        "confidence": 1.0,
    },
    "late_delivery_seller": {
        "cause": "SELLER_HANDOFF_AFTER_LIMIT",
        "party_type": "seller",
        "action": "refund_freight",
        "confidence": 1.0,
    },
    "late_delivery_logistics": {
        "cause": "CARRIER_DELIVERED_AFTER_ESTIMATE",
        "party_type": "logistics_provider",
        "party_id": "LOGISTICS_PROVIDER",
        "action": "refund_freight",
        "confidence": 1.0,
    },
    "valid_split_payment": {
        "cause": "MULTIPLE_PAYMENTS_RECONCILED",
        "action": "explain_valid_split_payment",
        "confidence": 1.0,
    },
    "unsupported_late_claim": {
        "cause": "DELIVERY_WITHIN_ESTIMATE",
        "action": "reject_late_refund",
        "confidence": 1.0,
    },
}
