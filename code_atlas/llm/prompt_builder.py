from typing import List

def build_prompt(query: str, context: List[str], max_context: int = 3) -> str:
    selected_context = "\n\n".join(context[:max_context])

    if not selected_context.strip():
        return f"No relevant code found in the graph for the question: {query}"

    return f"""
You are an intelligent code assistant.

Answer ONLY from the context below.
If the answer is not found in the context, say "I don't know".

Context:
{selected_context}

Question:
{query}

Answer:
""".strip()

# PURPOSE: Formats the retrieved Graph-Nodes into a clear instruction for the LLM.
