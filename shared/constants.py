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
