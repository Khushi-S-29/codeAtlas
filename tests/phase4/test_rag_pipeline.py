from code_atlas.retrieval.vector_search import Retriever
from code_atlas.llm.prompt_builder import build_prompt


def test_rag_pipeline_real():
    query = "What does add do?"

    retriever = Retriever()

    results = retriever.retrieve(query)

    assert len(results) > 0

    context = [r["text"] for r in results]

    prompt = build_prompt(query, context)

    assert isinstance(prompt, str)
    assert query.split()[0].lower() in prompt.lower()