"""
Abstract base agent (OCP + DIP).
Concrete agents extend this; callers depend on the interface, not implementations.
"""

from abc import ABC, abstractmethod
from typing import Any

import anthropic
from anthropic.types import TextBlock

from src.config import config


class BaseAgent(ABC):
 def __init__(self) -> None:
  self._client = anthropic.Anthropic(api_key=config.anthropic_api_key)
  self._model = config.anthropic_model
  self._resume = config.resume_text

 @abstractmethod
 def run(self, *args: Any, **kwargs: Any) -> Any:
  """Entry point for each agent's main task."""
  ...

 def _chat(self, system: str, user: str, max_tokens: int = 2048) -> str:
  """Single-turn LLM call with prompt caching on the system prompt."""
  message = self._client.messages.create(
   model=self._model,
   max_tokens=max_tokens,
   system=[
    {
     "type": "text",
     "text": system,
     # Prompt caching (SRP: caching here, not in callers).
     # System prompt is the largest stable block - cache it to save tokens
     # across multiple vacancy evaluations in the same scheduler run.
     "cache_control": {"type": "ephemeral"},
    }
   ],
   messages=[{"role": "user", "content": user}],
  )
  block = message.content[0]
  if not isinstance(block, TextBlock):
   raise ValueError(f"Expected TextBlock, got {type(block).__name__}")
  return block.text

 def _system_with_resume(self, instructions: str) -> str:
  """Prepend the candidate resume to any system prompt (DRY)."""
  return f"## Candidate Resume\n\n{self._resume}\n\n---\n\n{instructions}"
