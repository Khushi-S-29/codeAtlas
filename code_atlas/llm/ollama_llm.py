from ollama import Client

class OllamaLLM:
    def __init__(self, model: str = "llama2", host: str = "http://ollama:11434"):
        self.model = model
        self.client = Client(host=host)

    def ask(self, query: str, context: list[str]) -> str:
        context_str = "\n".join(context)
        prompt = f"Context:\n{context_str}\n\nQuestion: {query}\nAnswer:"
        
        try:
            response = self.client.chat(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}]
            )
            return response['message']['content']
        except Exception as e:
            return f"Ollama error: {str(e)}"

# PURPOSE: Acts as the direct bridge to the local Ollama server.