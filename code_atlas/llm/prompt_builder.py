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
You are an expert software engineer and code analyst.

Your ONLY source of truth is the retrieved code below.

========================
INSTRUCTIONS
========================

1. Analyze only the retrieved context provided.

2. If the question mentions a specific function, method, class, variable, or file name:
   - Find the EXACT matching name in the retrieved context.
   - If an exact match exists, answer ONLY using that code.
   - Ignore unrelated retrieved code.
   - Do NOT describe another function with a similar purpose.

3. If the exact function is NOT present in the retrieved context:
   - Clearly state:
     "The requested function was not found in the retrieved context."
   - Do NOT guess.
   - Do NOT use outside knowledge.

4. Explain only what is visible in the retrieved code.

5. Mention:
   - function name
   - file name
   - parameters (if available)
   - return value (if available)
   - important function calls
   - important logic
   - exceptions or error handling
   - interactions with other functions shown in the context

6. If the function calls another retrieved function, explain that relationship.

7. Never invent:
   - missing code
   - hidden implementation
   - architecture
   - data flow
   - APIs
   - variables

8. If the retrieved context is incomplete, explicitly say which information is missing.

9. Answer in concise technical language.

10. For every claim, mention the code element that supports it.

For conceptual questions:
- summarize only concepts explicitly present in retrieved code.
- do not infer components outside the context.

========================
RETRIEVED CODE
========================
Context:
{selected_context}

Question:
{query}

Technical Explanation:
""".strip()