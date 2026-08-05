import json
from pathlib import Path

import pytest

from services.model_client import QwenModelClient
from shared.constants import MODEL_NAME, MODEL_PARAMETER_SIZE_BILLION


ROOT = Path(__file__).resolve().parents[1]


def test_qwen_model_is_declared_and_within_parameter_limit() -> None:
    assert MODEL_NAME == "Qwen/Qwen2.5-1.5B-Instruct"
    assert MODEL_PARAMETER_SIZE_BILLION <= 10


def test_metadata_matches_source_configuration() -> None:
    metadata = json.loads((ROOT / "logging" / "metadata.json").read_text())
    assert metadata["model"] == MODEL_NAME
    assert metadata["parameter_size_billion"] == MODEL_PARAMETER_SIZE_BILLION
    assert metadata["framework"] == "transformers"
    assert metadata["runtime"] == "local"


def test_model_client_rejects_empty_messages_without_loading_weights() -> None:
    client = QwenModelClient()
    with pytest.raises(ValueError, match="must not be empty"):
        client.generate([])
