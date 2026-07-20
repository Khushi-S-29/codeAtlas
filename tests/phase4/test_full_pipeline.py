from code_atlas.retrieval.vector_search import Retriever
from code_atlas.llm.prompt_builder import build_prompt


def test_full_pipeline_real():
    query = "What functions are present?"

    retriever = Retriever()

    results = retriever.retrieve(query)

    assert len(results) > 0

    context = [r["text"] for r in results]

    prompt = build_prompt(query, context)

    assert "function" in prompt.lower()
    assert isinstance(prompt, str)