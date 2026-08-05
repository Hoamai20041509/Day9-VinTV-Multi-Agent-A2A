"""Application-wide constants that must be visible during grading."""

# Lightweight instruct model (well under the 10B-parameter cap) chosen to keep
# download time and per-case latency small; weights are cached locally.
MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"
MODEL_PARAMETER_SIZE_BILLION = 1.54
MODEL_FRAMEWORK = "transformers"
MODEL_RUNTIME = "local"

# Agents run short structured tasks: greedy decoding keeps the trace
# reproducible run-to-run and avoids sampling noise in narrations.
MODEL_ENABLE_THINKING = False
MODEL_DO_SAMPLE = False
MODEL_MAX_NEW_TOKENS = 64
MODEL_TEMPERATURE = 0.7
MODEL_TOP_P = 0.8
MODEL_TOP_K = 20

# EC_POLICY_V1 business constants.
POLICY_VERSION = "EC_POLICY_V1"
RECONCILIATION_TOLERANCE_BRL = 0.10
CURRENCY = "BRL"
PLATFORM_PARTY_ID = "OLIST_PLATFORM"
LOGISTICS_PARTY_ID = "LOGISTICS_PROVIDER"

# Output schema caps from the assignment brief.
MAX_ENTITY_IDS = 5
MAX_EVIDENCE_IDS = 10
MAX_RANKED_CAUSES = 3
MAX_RESPONSIBLE_PARTIES = 3
MAX_RESOLUTION_ACTIONS = 5
