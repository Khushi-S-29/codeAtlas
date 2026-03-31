from code_atlas.llm.prompt_builder import build_prompt


def test_prompt_contains_query_and_context():
    query = "What is add?"
    context = ["def add(a,b): return a+b"]

    prompt = build_prompt(query, context)

    assert "add" in prompt
    assert "Context" in prompt
    assert "Question" in prompt
    assert "Answer" in prompt


def test_prompt_limits_context():
    context = ["c1", "c2", "c3"]

    prompt = build_prompt("test", context, max_context=2)

    assert "c1" in prompt
    assert "c2" in prompt
    assert "c3" not in prompt


def test_prompt_empty_context():
    prompt = build_prompt("test", [])

    assert isinstance(prompt, str)
    assert "No relevant code found" in prompt