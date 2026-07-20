from code_atlas.llm.prompt_builder import build_prompt


def test_empty_query():
    prompt = build_prompt("", ["context"])

    assert isinstance(prompt, str)


def test_empty_context():
    prompt = build_prompt("test", [])

    assert "No relevant code found" in prompt