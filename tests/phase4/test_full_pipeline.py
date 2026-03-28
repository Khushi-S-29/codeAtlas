from code_atlas.retrieval.vector_search import Retriever
from code_atlas.llm.llm_query import LLMQuery
from code_atlas.llm.prompt_builder import build_prompt

def test_full_pipeline_real():
    query = "What functions are present?"

    retriever = Retriever()

    results = retriever.retrieve(query)
    context = [r["text"] for r in results]

    llm = LLMQuery()
    prompt = build_prompt(query, context)
    
    answer = llm.ask(query, context)

    assert len(context) > 0, "Should retrieve at least one code snippet"
    assert "function" in prompt.lower(), "Prompt should contain the word function"
    assert isinstance(answer, str), "Answer should be a string"