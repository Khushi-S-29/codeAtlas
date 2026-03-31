from typing import List

def build_prompt(query: str, context: List[str], max_context: int = 3) -> str:
    selected_context = "\n\n---\n\n".join(context[:max_context])

    if not selected_context.strip():
        return f"""
No relevant code found
Question:
{query}

Answer:
I don't know.
""".strip()

    return f"""
You are a senior software engineer analyzing a codebase.

Your task is to READ the function-level code and EXPLAIN how it works.

STRICT RULES:
- You are given FUNCTION LEVEL code
- Explain exactly what the function does
- Do NOT generalize across files
- Focus only on given function
- Answer ONLY from given code
- Do NOT hallucinate
- Be precise and technical

Context:
{selected_context}

Question:
{query}

Answer (step-by-step):
""".strip()