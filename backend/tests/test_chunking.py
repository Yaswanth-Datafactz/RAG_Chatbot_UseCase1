from app.services.chunking import (
    TARGET_CHUNK_TOKENS,
    Chunk,
    ParsedSection,
    _split_sentences,
    chunk_sections,
)


def test_short_section_becomes_a_single_chunk():
    sections = [ParsedSection(heading_path=("Doc", "Section A"), text="This is a short sentence. Another one.")]

    chunks = chunk_sections(sections)

    assert len(chunks) == 1
    assert chunks[0].section_path == "Doc > Section A"
    assert chunks[0].chunk_index == 0


def test_heading_change_forces_a_new_chunk_even_if_small():
    sections = [
        ParsedSection(heading_path=("Doc", "Section A"), text="Short sentence A."),
        ParsedSection(heading_path=("Doc", "Section B"), text="Short sentence B."),
    ]

    chunks = chunk_sections(sections)

    assert len(chunks) == 2
    assert chunks[0].section_path == "Doc > Section A"
    assert chunks[1].section_path == "Doc > Section B"
    assert "sentence B" not in chunks[0].content
    assert "sentence A" not in chunks[1].content


def test_no_chunk_contains_text_from_two_sections():
    # Regression guard: overlap must never bleed across a heading boundary.
    long_a = " ".join(f"Sentence A{i} has some words in it." for i in range(70))
    long_b = " ".join(f"Sentence B{i} has some words in it." for i in range(10))
    sections = [
        ParsedSection(heading_path=("Doc", "Section A"), text=long_a),
        ParsedSection(heading_path=("Doc", "Section B"), text=long_b),
    ]

    chunks = chunk_sections(sections)

    a_chunks = [c for c in chunks if c.section_path == "Doc > Section A"]
    b_chunks = [c for c in chunks if c.section_path == "Doc > Section B"]
    assert len(a_chunks) > 1, "section A should have been long enough to split into multiple chunks"
    for c in a_chunks:
        assert "Sentence B" not in c.content
    for c in b_chunks:
        assert "Sentence A" not in c.content


def test_oversized_section_splits_into_multiple_overlapping_chunks():
    long_text = " ".join(f"This is sentence number {i} in a long policy section." for i in range(60))
    sections = [ParsedSection(heading_path=("Doc", "Big Section"), text=long_text)]

    chunks = chunk_sections(sections)

    assert len(chunks) > 1
    for c in chunks:
        assert c.section_path == "Doc > Big Section"
        assert c.token_count <= TARGET_CHUNK_TOKENS * 1.5  # generous ceiling; no wild blowups
    # Consecutive chunks should overlap: the first sentence of chunk[i+1]
    # should already appear at the tail of chunk[i].
    for i in range(len(chunks) - 1):
        first_sentence_of_next = _split_sentences(chunks[i + 1].content)[0]
        assert first_sentence_of_next in chunks[i].content


def test_never_splits_mid_sentence():
    long_text = " ".join(f"This is sentence number {i} in a long policy section." for i in range(60))
    sections = [ParsedSection(heading_path=("Doc", "Big Section"), text=long_text)]
    all_sentences = set(_split_sentences(long_text))

    chunks = chunk_sections(sections)

    for c in chunks:
        for sentence in _split_sentences(c.content):
            assert sentence in all_sentences, f"fragment is not a whole sentence: {sentence!r}"


def test_single_oversized_sentence_is_kept_whole_even_if_it_exceeds_target():
    huge_sentence = (
        "This is one absurdly long single sentence about company policy that "
        + ("goes on and on " * 200)
        + "and finally ends."
    )
    sections = [ParsedSection(heading_path=("Doc", "Section"), text=huge_sentence)]

    chunks = chunk_sections(sections)

    assert len(chunks) == 1
    assert chunks[0].content == huge_sentence
    assert chunks[0].token_count > TARGET_CHUNK_TOKENS, "should accept the overage rather than split the sentence"


def test_empty_section_text_produces_no_chunks():
    sections = [ParsedSection(heading_path=("Doc", "Empty"), text="   ")]

    assert chunk_sections(sections) == []


def test_chunk_index_is_sequential_across_the_whole_document():
    sections = [
        ParsedSection(heading_path=("Doc", "A"), text="Sentence one. Sentence two."),
        ParsedSection(heading_path=("Doc", "B"), text="Sentence three. Sentence four."),
    ]

    chunks = chunk_sections(sections)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_decimal_numbers_and_emails_do_not_cause_false_sentence_splits():
    text = (
        "Full-time employees accrue PTO at 1.67 days per month during their first three years. "
        "Contact hr@contoso-corp.example with questions. The rate increases in year four."
    )
    sections = [ParsedSection(heading_path=("Doc", "PTO"), text=text)]

    chunks = chunk_sections(sections)

    assert len(chunks) == 1
    assert "1.67 days" in chunks[0].content
    assert "hr@contoso-corp.example" in chunks[0].content
