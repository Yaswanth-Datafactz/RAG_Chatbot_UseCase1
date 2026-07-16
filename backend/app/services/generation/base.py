"""Generation adapter interface (docs/plan.md Decision #4): one interface,
two real implementations (Claude, Azure OpenAI), selected by
GENERATION_PROVIDER so switching providers is a config change, not a
rewrite.

Both methods are async, since every call here is a live LLM network
request (Handbook §6.2: async I/O for all LLM/network calls):
- complete(): a single non-streaming completion. This is what
  services/rewrite.py's `generate_fn` needs -- the standalone-query
  rewrite is a quick, one-shot turnaround the user never watches stream
  in, not the answer itself.
- stream(): an async generator of text deltas, used for the chat answer
  (Decision #10: citations arrive before this token stream starts).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class GenerationAdapter(ABC):
    model_name: str

    @abstractmethod
    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Single non-streaming completion."""

    @abstractmethod
    def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        """Yields text deltas as they're generated."""
