"""Application-wide constants that must be visible during grading."""

from decimal import Decimal


POLICY_VERSION = "EC_POLICY_V1"
CURRENCY_BRL = "BRL"
MONEY_TOLERANCE_BRL = Decimal("0.10")

ISSUE_VALID_SPLIT_PAYMENT = "valid_split_payment"
ROOT_CAUSE_MULTIPLE_PAYMENTS_RECONCILED = "MULTIPLE_PAYMENTS_RECONCILED"
ACTION_EXPLAIN_VALID_SPLIT_PAYMENT = "explain_valid_split_payment"

RESPONSIBLE_PARTY_NONE = "none"

MAX_ENTITY_IDS = 5
MAX_EVIDENCE_IDS = 10
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
