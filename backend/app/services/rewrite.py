"""Standalone-query rewrite (docs/plan.md Decision #7): collapses the last
3 conversation turns plus the new question into one standalone query, so a
follow-up like "what about for contractors?" retrieves correctly without
needing conversation context threaded through search/embedding.

The rewrite itself needs a generation call. Phase 4 owns building the real
generation adapter (services/generation/{base,claude,azure_openai}.py,
Decision #4) -- that doesn't exist yet, and building it here would jump
ahead of this phase's scope. So rewrite_query() takes a plain
`generate_fn: Callable[[str], str]` the same way Phase 2's ingestion.py
takes an injectable embedding_client/search_repo_module: Phase 4 will pass
its adapter's non-streaming completion call as this argument. Tests fake
this callable exactly like Phase 2 faked Search and embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

HISTORY_TURNS = 3  # Decision #7: last 3 turns verbatim

GenerateFn = Callable[[str], str]

_REWRITE_PROMPT_TEMPLATE = """Rewrite the final user question as a standalone question that can be understood without the conversation history below. Preserve its original meaning and intent exactly. Do not answer the question -- only rewrite it. If it is already standalone, return it unchanged. Respond with only the rewritten question, nothing else.

Conversation history:
{history}

Final question: {question}

Standalone question:"""


@dataclass
class Turn:
    """One prior conversation exchange: a user question and the assistant's
    answer to it."""

    question: str
    answer: str


def _format_history(history: list[Turn]) -> str:
    lines = []
    for turn in history:
        lines.append(f"User: {turn.question}")
        lines.append(f"Assistant: {turn.answer}")
    return "\n".join(lines)


def rewrite_query(history: list[Turn], question: str, generate_fn: GenerateFn) -> str:
    """Returns a standalone version of `question`. If there is no prior
    history, the question is already standalone by definition and the
    generation call is skipped entirely."""
    if not history:
        return question

    recent = history[-HISTORY_TURNS:]
    prompt = _REWRITE_PROMPT_TEMPLATE.format(history=_format_history(recent), question=question)

    rewritten = generate_fn(prompt).strip()
    return rewritten if rewritten else question
