import json
from pathlib import Path

import pytest

from app.services.parsing import parse_docx, parse_document, parse_markdown, parse_pdf

CORPUS_DIR = Path(__file__).resolve().parents[2] / "corpus"
MANIFEST = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))


def test_parse_markdown_recovers_title_section_subsection(tmp_path):
    md_path = tmp_path / "doc.md"
    md_path.write_text(
        "# Doc Title\n\n"
        "## Section One\n\n"
        "Intro sentence for section one.\n\n"
        "### Sub One\n\n"
        "Sub one content here.\n\n"
        "## Section Two\n\n"
        "Section two content.\n",
        encoding="utf-8",
    )

    sections = parse_markdown(md_path)

    paths = [s.heading_path for s in sections]
    assert ("Doc Title", "Section One", "Sub One") in paths
    assert ("Doc Title", "Section Two") in paths
    sub_one = next(s for s in sections if s.heading_path == ("Doc Title", "Section One", "Sub One"))
    assert sub_one.text == "Sub one content here."


def test_parse_markdown_section_with_no_own_paragraphs_is_not_emitted(tmp_path):
    md_path = tmp_path / "doc.md"
    md_path.write_text(
        "# Doc Title\n\n## Parent Section\n\n### Only Child\n\nChild text.\n",
        encoding="utf-8",
    )

    sections = parse_markdown(md_path)

    paths = [s.heading_path for s in sections]
    assert ("Doc Title", "Parent Section") not in paths
    assert ("Doc Title", "Parent Section", "Only Child") in paths


def test_parse_docx_reads_real_word_heading_styles():
    sections = parse_docx(CORPUS_DIR / "pto-and-leave-policy.docx")

    paths = [s.heading_path for s in sections]
    assert ("Contoso Corp Paid Time Off and Leave Policy", "Overview of Leave Types") in paths
    assert (
        "Contoso Corp Paid Time Off and Leave Policy",
        "Paid Time Off (PTO)",
        "Accrual Rates",
    ) in paths
    accrual = next(s for s in sections if s.heading_path[-1] == "Accrual Rates")
    assert "6.15 hours per pay period" in accrual.text


def test_parse_pdf_recovers_headings_via_font_size_and_tracks_page_no():
    sections = parse_pdf(CORPUS_DIR / "compensation-and-pay-practices-policy.pdf")

    paths = [s.heading_path for s in sections]
    assert ("Contoso Corp Compensation and Pay Practices Policy", "Pay Grades and Structure") in paths
    assert all(s.page_no is not None for s in sections)


@pytest.mark.parametrize("entry", MANIFEST["documents"], ids=lambda e: e["filename"])
def test_every_corpus_document_parses_to_its_manifest_outline(entry):
    sections = parse_document(CORPUS_DIR / entry["filename"], entry["type"])
    assert sections, f"{entry['filename']} produced no sections"

    title = entry["title"]
    parsed_pairs = set()
    for s in sections:
        assert s.heading_path[0] == title
        if len(s.heading_path) == 2:
            parsed_pairs.add((s.heading_path[1], None))
        elif len(s.heading_path) == 3:
            parsed_pairs.add((s.heading_path[1], s.heading_path[2]))
        else:
            raise AssertionError(f"unexpected heading depth: {s.heading_path}")

    # A section with subsections can *also* carry its own directly-attached
    # paragraphs (an intro before the first subsection) -- generate_corpus.py's
    # per-section "paragraphs" and "subsections" are independent, and the
    # parser correctly emits that intro content as its own (heading, None)
    # chunk rather than silently dropping it. manifest.json's outline doesn't
    # record whether a section has its own paragraphs (only its heading and
    # subsection headings), so (heading, None) is REQUIRED when a section has
    # no subsections, but only ALLOWED (not required) when it does.
    required_pairs = set()
    allowed_pairs = set()
    for outline_entry in entry["section_outline"]:
        heading = outline_entry["heading"]
        subs = outline_entry["subsections"]
        if subs:
            for sub in subs:
                required_pairs.add((heading, sub))
            allowed_pairs.add((heading, None))
        else:
            required_pairs.add((heading, None))
    allowed_pairs |= required_pairs

    missing = required_pairs - parsed_pairs
    assert not missing, f"manifest-required sections/subsections not recovered by the parser: {missing}"
    unexpected = parsed_pairs - allowed_pairs
    assert not unexpected, f"parser recovered headings not present in manifest.json's outline: {unexpected}"
