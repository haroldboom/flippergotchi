from __future__ import annotations

from abc import ABC, abstractmethod


class AIBackend(ABC):
    """A text-generation backend for the pet's voice and capture analysis."""

    name = "base"
    available = False

    @abstractmethod
    def generate(self, system: str, user: str, max_tokens: int = 60) -> str:
        ...
