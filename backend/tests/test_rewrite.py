from app.services.rewrite import HISTORY_TURNS, Turn, rewrite_query


def test_no_history_returns_question_unchanged_without_calling_generate_fn():
    def _should_not_be_called(prompt: str) -> str:
        raise AssertionError("generate_fn must not be called when there is no history")

    result = rewrite_query([], "What is the PTO policy?", _should_not_be_called)

    assert result == "What is the PTO policy?"


def test_history_and_question_are_both_included_in_the_prompt():
    captured_prompts = []

    def _fake_generate(prompt: str) -> str:
        captured_prompts.append(prompt)
        return "What is Contoso's PTO policy for full-time employees?"

    history = [Turn(question="What is Contoso's PTO policy?", answer="Full-time employees accrue 15 days/year.")]

    result = rewrite_query(history, "What about for contractors?", _fake_generate)

    assert result == "What is Contoso's PTO policy for full-time employees?"
    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "What is Contoso's PTO policy?" in prompt
    assert "Full-time employees accrue 15 days/year." in prompt
    assert "What about for contractors?" in prompt


def test_only_the_last_history_turns_are_included():
    history = [Turn(question=f"Question {i}", answer=f"Answer {i}") for i in range(5)]
    captured_prompts = []

    def _fake_generate(prompt: str) -> str:
        captured_prompts.append(prompt)
        return "standalone question"

    rewrite_query(history, "final question", _fake_generate)

    prompt = captured_prompts[0]
    # Only the last HISTORY_TURNS (3) turns should appear -- the older ones
    # (indices 0, 1) must be dropped.
    for i in range(5 - HISTORY_TURNS):
        assert f"Question {i}" not in prompt
    for i in range(5 - HISTORY_TURNS, 5):
        assert f"Question {i}" in prompt


def test_blank_generation_response_falls_back_to_original_question():
    history = [Turn(question="What is Contoso's PTO policy?", answer="15 days/year.")]

    result = rewrite_query(history, "What about for contractors?", lambda prompt: "   ")

    assert result == "What about for contractors?"
