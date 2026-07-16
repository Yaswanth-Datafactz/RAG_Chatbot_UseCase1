"""Structure-aware chunker (docs/plan.md Decision #1).

~512 tokens/chunk, ~64-token (~12%) overlap. Section boundaries are hard
breaks: overlap never bleeds from one heading into the next, because that
would blur which section_path a chunk's tail actually belongs to, and
citations depend on section_path being accurate. Chunk boundaries always
fall on a sentence boundary, even in the pathological case where a single
sentence alone exceeds the target chunk size -- that sentence is kept
whole rather than split.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

TARGET_CHUNK_TOKENS = 512
OVERLAP_TOKENS = 64
_ENCODING_NAME = "cl100k_base"

# Split after a sentence-ending punctuation mark followed by whitespace,
# only when the next visible character looks like the start of a new
# sentence. This avoids splitting on decimals ("1.67 days") and on
# abbreviations/emails with no following whitespace ("hr@contoso.example").
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")

_encoding = tiktoken.get_encoding(_ENCODING_NAME)


def _count_tokens(text: str) -> int:
    return len(_encoding.encode(text))


def _split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


@dataclass
class ParsedSection:
    """One leaf section from a parsed document: its full heading path
    (document title first, then section, then optional subsection) and
    its own prose text (not including any subsections' text)."""

    heading_path: tuple[str, ...]
    text: str
    page_no: int | None = None


@dataclass
class Chunk:
    content: str
    section_path: str
    token_count: int
    chunk_index: int
    page_no: int | None = None


def chunk_sections(sections: list[ParsedSection]) -> list[Chunk]:
    """Turns parsed leaf sections into chunks. chunk_index is sequential
    across the whole document (not reset per section)."""
    chunks: list[Chunk] = []
    chunk_index = 0
    for section in sections:
        section_path = " > ".join(section.heading_path)
        sentences = _split_sentences(section.text)
        if not sentences:
            continue
        sentence_tokens = [_count_tokens(s) for s in sentences]
        for piece in _pack_sentences(sentences, sentence_tokens):
            content = " ".join(piece)
            chunks.append(
                Chunk(
                    content=content,
                    section_path=section_path,
                    token_count=_count_tokens(content),
                    chunk_index=chunk_index,
                    page_no=section.page_no,
                )
            )
            chunk_index += 1
    return chunks


def _pack_sentences(sentences: list[str], sentence_tokens: list[int]) -> list[list[str]]:
    """Greedily packs sentences into ~TARGET_CHUNK_TOKENS windows with
    ~OVERLAP_TOKENS of trailing-sentence overlap between consecutive
    windows. Operates within a single section only -- callers must not
    mix sentences from different sections into one call."""
    windows: list[list[str]] = []
    start = 0
    n = len(sentences)
    while start < n:
        end, _ = _grow_window(start, n, sentence_tokens)
        windows.append(sentences[start:end])
        if end >= n:
            break
        start = _next_start_with_overlap(start, end, sentence_tokens)
    return windows


def _grow_window(start: int, n: int, sentence_tokens: list[int]) -> tuple[int, int]:
    """Extends a window forward from `start` while the running token total
    stays within TARGET_CHUNK_TOKENS. The first sentence is always
    included regardless of its size, so a single oversized sentence is
    still emitted (whole) rather than dropped or split."""
    end = start
    total = 0
    while end < n:
        candidate = total + sentence_tokens[end]
        if end > start and candidate > TARGET_CHUNK_TOKENS:
            break
        total = candidate
        end += 1
    return end, total


def _next_start_with_overlap(start: int, end: int, sentence_tokens: list[int]) -> int:
    """Walks back from `end` accumulating up to OVERLAP_TOKENS of trailing
    sentences, but never walks back past start + 1 -- that guarantees the
    window always advances by at least one sentence, so packing always
    terminates even when overlap can't fit (e.g. the first sentence of the
    next window is itself larger than OVERLAP_TOKENS)."""
    overlap_start = end
    overlap_total = 0
    floor = start + 1
    while overlap_start > floor:
        candidate = sentence_tokens[overlap_start - 1]
        if overlap_total + candidate > OVERLAP_TOKENS:
            break
        overlap_total += candidate
        overlap_start -= 1
    return overlap_start
