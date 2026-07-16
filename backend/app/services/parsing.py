"""Per-format parsers that normalize PDF/DOCX/Markdown into the same
ParsedSection shape chunking.py operates on.

Not named in docs/plan.md's Phase 2 bullet list (which names search_repo.py,
chunking.py, embedding.py, ingestion.py) -- this module exists so "load then
parse" is its own layer rather than being inlined into ingestion.py, per
Handbook 6.2's layered-backend standard. See docs/phase-2.md.

Every parser recovers the same Title > Section > Subsection heading path
used to build the corpus (docs/phase-1.md): Markdown from '#'/'##'/'###',
DOCX from real Word paragraph styles ('Title'/'Heading 1'/'Heading 2'),
and PDF from font size, ranked dynamically per document (the largest
distinct size is the title, the next-largest is a section heading, and so
on down to whichever size has the most total words -- that one is body
text) so this doesn't depend on the exact point sizes corpus/generate_corpus.py
happened to use.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument
from markdown_it import MarkdownIt

from app.services.chunking import ParsedSection

_md = MarkdownIt()


def parse_markdown(path: Path) -> list[ParsedSection]:
    text = Path(path).read_text(encoding="utf-8")
    tokens = _md.parse(text)

    sections: list[ParsedSection] = []
    heading_stack: list[str] = []
    current_paragraphs: list[str] = []

    def flush() -> None:
        if heading_stack and current_paragraphs:
            sections.append(
                ParsedSection(heading_path=tuple(heading_stack), text=" ".join(current_paragraphs))
            )
        current_paragraphs.clear()

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            flush()
            level = int(tok.tag[1])  # 'h1' -> 1, 'h2' -> 2, ...
            i += 1
            heading_text = tokens[i].content
            heading_stack[:] = heading_stack[: level - 1]
            heading_stack.append(heading_text)
        elif tok.type == "paragraph_open":
            i += 1
            current_paragraphs.append(tokens[i].content)
        i += 1
    flush()
    return sections


def parse_docx(path: Path) -> list[ParsedSection]:
    document = DocxDocument(str(path))

    sections: list[ParsedSection] = []
    heading_stack: list[str] = []
    current_paragraphs: list[str] = []

    def flush() -> None:
        if heading_stack and current_paragraphs:
            sections.append(
                ParsedSection(heading_path=tuple(heading_stack), text=" ".join(current_paragraphs))
            )
        current_paragraphs.clear()

    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = para.style.name if para.style else "Normal"
        if style_name == "Title":
            flush()
            heading_stack[:] = [text]
        elif style_name.startswith("Heading"):
            level = int(style_name.split()[-1])  # "Heading 1" -> 1, "Heading 2" -> 2
            flush()
            heading_stack[:] = heading_stack[:level]
            heading_stack.append(text)
        else:
            current_paragraphs.append(text)
    flush()
    return sections


def parse_pdf(path: Path) -> list[ParsedSection]:
    import pdfplumber

    lines: list[tuple[int, str, float]] = []  # (page_no, text, font_size)
    with pdfplumber.open(str(path)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(extra_attrs=["size"])
            lines.extend(_group_words_into_lines(words, page_no))

    if not lines:
        return []

    word_count_by_size: dict[float, int] = {}
    for _, text, size in lines:
        word_count_by_size[size] = word_count_by_size.get(size, 0) + len(text.split())
    body_size = max(word_count_by_size, key=word_count_by_size.get)
    heading_sizes = sorted((s for s in word_count_by_size if s > body_size), reverse=True)
    level_by_size = {size: level for level, size in enumerate(heading_sizes)}

    sections: list[ParsedSection] = []
    heading_stack: list[str] = []
    current_paragraphs: list[str] = []
    current_page_no: int | None = None
    last_heading_level: int | None = None

    def flush() -> None:
        if heading_stack and current_paragraphs:
            sections.append(
                ParsedSection(
                    heading_path=tuple(heading_stack),
                    text=" ".join(current_paragraphs),
                    page_no=current_page_no,
                )
            )
        current_paragraphs.clear()

    for page_no, text, size in lines:
        if size in level_by_size:
            level = level_by_size[size]
            if level == last_heading_level:
                # Continuation of a word-wrapped heading (same font size,
                # immediately follows the previous heading line with no
                # body text in between) -- concatenate, don't start a new
                # heading entry.
                heading_stack[-1] = f"{heading_stack[-1]} {text}"
            else:
                flush()
                heading_stack[:] = heading_stack[:level]
                heading_stack.append(text)
            last_heading_level = level
        else:
            if not current_paragraphs:
                current_page_no = page_no
            current_paragraphs.append(text)
            last_heading_level = None
    flush()
    return sections


def _group_words_into_lines(
    words: list[dict], page_no: int, tolerance: float = 2.0
) -> list[tuple[int, str, float]]:
    lines: list[tuple[int, str, float]] = []
    current_top: float | None = None
    current_words: list[str] = []
    current_size: float | None = None

    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        top = w["top"]
        if current_top is None or abs(top - current_top) > tolerance:
            if current_words:
                lines.append((page_no, " ".join(current_words), current_size))
            current_words = [w["text"]]
            current_top = top
            current_size = round(w["size"], 1)
        else:
            current_words.append(w["text"])
    if current_words:
        lines.append((page_no, " ".join(current_words), current_size))
    return lines


_PARSERS = {
    "markdown": parse_markdown,
    "docx": parse_docx,
    "pdf": parse_pdf,
}


def parse_document(path: Path, doc_type: str) -> list[ParsedSection]:
    try:
        parser = _PARSERS[doc_type]
    except KeyError:
        raise ValueError(f"Unsupported doc_type: {doc_type!r}") from None
    return parser(path)
