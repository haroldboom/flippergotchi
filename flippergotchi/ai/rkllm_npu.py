from __future__ import annotations

from .base import AIBackend


class RkllmBackend(AIBackend):
    """NPU-accelerated LLM via the Rockchip RKLLM runtime (RK3576 6 TOPS NPU).

    STATUS: stub. The RK3576 NPU needs the mainline 'rocket' driver + RKLLM
    runtime, which are not shipping yet (tracked in
    flipperdevices/flipperone-linux-build-scripts#55). When they land:
      - convert a sub-3B model (Qwen2.5-1.5B / Llama-3.2-1B) to .rkllm
      - load it here via the rkllm runtime and stream tokens in generate()
    Until then build_backend() catches the error and falls back to canned/cpu.
    """

    name = "rkllm-npu"

    def __init__(self, cfg):
        self.cfg = cfg
        self.available = False
        # TODO: from rkllm_runtime import RKLLM; self._m = RKLLM(cfg.ai_model_path)
        raise NotImplementedError(
            "RKLLM NPU backend not available until the RK3576 NPU driver ships"
        )

    def generate(self, system: str, user: str, max_tokens: int = 60) -> str:
        raise NotImplementedError
