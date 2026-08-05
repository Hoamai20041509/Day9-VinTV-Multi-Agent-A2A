"""Lazy local inference client for the configured Qwen model."""

from __future__ import annotations

from typing import Any, Sequence

from shared.constants import (
    MODEL_DO_SAMPLE,
    MODEL_ENABLE_THINKING,
    MODEL_MAX_NEW_TOKENS,
    MODEL_NAME,
    MODEL_TEMPERATURE,
    MODEL_TOP_K,
    MODEL_TOP_P,
)


class QwenModelClient:
    """Load the configured Qwen model only when generation is requested.

    Keeping model loading lazy allows repository and policy tests to run without
    downloading the model weights or allocating accelerator memory.
    """

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model_name = model_name
        self._tokenizer: Any = None
        self._model: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Model dependencies are missing; run pip install -r requirements.txt"
            ) from exc

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype="auto",
            device_map="auto",
        )

    def generate(
        self,
        messages: Sequence[dict[str, str]],
        *,
        enable_thinking: bool = MODEL_ENABLE_THINKING,
        max_new_tokens: int = MODEL_MAX_NEW_TOKENS,
    ) -> str:
        """Generate the final answer for an OpenAI-style message sequence."""
        if not messages:
            raise ValueError("messages must not be empty")
        self._load()

        prompt = self._tokenizer.apply_chat_template(
            list(messages),
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=enable_thinking,
        )
        model_inputs = self._tokenizer([prompt], return_tensors="pt").to(
            self._model.device
        )
        sampling_kwargs = (
            {"temperature": MODEL_TEMPERATURE, "top_p": MODEL_TOP_P, "top_k": MODEL_TOP_K}
            if MODEL_DO_SAMPLE
            else {}
        )
        generated_ids = self._model.generate(
            **model_inputs,
            max_new_tokens=max_new_tokens,
            do_sample=MODEL_DO_SAMPLE,
            **sampling_kwargs,
        )
        output_ids = generated_ids[0][len(model_inputs.input_ids[0]) :]
        response = self._tokenizer.decode(output_ids, skip_special_tokens=True)

        # Qwen may include a thinking block when callers explicitly enable it.
        if "</think>" in response:
            response = response.split("</think>", maxsplit=1)[1]
        return response.strip()
