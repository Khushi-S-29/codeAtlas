from typing import List
from code_atlas.llm.ollama_llm import OllamaLLM
from code_atlas.llm.prompt_builder import build_prompt

class LLMQuery:
    """
    Handles LLM-based question answering by combining context and prompt logic.
    """
    def __init__(self, model: str = "llama2", host: str = "http://ollama:11434"):
        self.llm = OllamaLLM(model=model, host=host)

    def ask(self, query: str, context: List[str]) -> str:
        if not query.strip():
            return "Please provide a valid question."

        final_prompt = build_prompt(query, context)
        
        return self.llm.client.chat(
            model=self.llm.model,
            messages=[{'role': 'user', 'content': final_prompt}]
        )['message']['content']

# PURPOSE: Orchestrates the prompt creation and the LLM response.