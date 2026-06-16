from __future__ import annotations

import os

from .base import AIBackend


class LlamaCppBackend(AIBackend):
    """Small GGUF model on the CPU via llama-cpp-python.

    This is the launch-day AI backend: it runs today on the RK3576 Cortex-A72
    cores (slow, but fine for one-line reactions) and on any dev laptop. Swap to
    RkllmBackend once the NPU 'rocket' driver ships. See README -> "AI backends".
    """

    name = "cpu-llama"

    def __init__(self, cfg):
        self.cfg = cfg
        self.available = False
        model = os.path.expanduser(cfg.ai_model_path or "")
        if not model or not os.path.exists(model):
            raise FileNotFoundError(
                "set ai_model_path to a .gguf (e.g. Qwen2.5-1.5B-Instruct-Q4)"
            )
        try:
            from llama_cpp import Llama  # optional dependency
        except ImportError as e:
            raise ImportError("pip install llama-cpp-python") from e
        self._llm = Llama(model_path=model, n_ctx=512, verbose=False)
        self.available = True

    def generate(self, system: str, user: str, max_tokens: int = 60) -> str:
        out = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.9,
        )
        return out["choices"][0]["message"]["content"]
