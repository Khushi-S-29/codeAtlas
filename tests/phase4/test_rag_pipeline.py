from code_atlas.retrieval.vector_search import Retriever
from code_atlas.llm.llm_query import LLMQuery
from code_atlas.llm.prompt_builder import build_prompt

def test_rag_pipeline_real():
    query = "What does add do?"

    retriever = Retriever()
    
    results = retriever.retrieve(query)
    
    context = [r["text"] for r in results]

    llm = LLMQuery()
    
    prompt = build_prompt(query, context)
    answer = llm.ask(query, context)

    assert isinstance(answer, str), "LLM answer should be a string"
    assert len(answer) > 0, "LLM answer should not be empty"
    assert query.split()[0].lower() in prompt.lower(), "Prompt should contain the original query"