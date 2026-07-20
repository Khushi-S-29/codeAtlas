from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import List, Optional
import os

from code_atlas.query.rag_query import RAGQuery
from code_atlas.llm.llm_query import LLMQuery
from code_atlas.query.langchain_rag import LangChainRAG

API_KEY = os.getenv("API_KEY", "mysecret123s") 
app = FastAPI(title="CodeAtlas API", version="1.0")


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-KEY")):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return x_api_key

rag = RAGQuery()
llm = LLMQuery(model="llama2")
langchain_rag = LangChainRAG()

class QueryRequest(BaseModel):
    query: str
    k: Optional[int] = 3

class QueryResponse(BaseModel):
    answer: str
    context: List[str]

class LangChainResponse(BaseModel):
    query: str
    answer: str


@app.get("/")
def root():
    return {"status": "CodeAtlas running", "mode": "Graph-RAG"}

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest, _: str = Depends(verify_api_key)):
    """Standard RAG pipeline: Retrieve from Graph -> Generate with LLM"""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Empty query")

    context = rag.retrieve(req.query, k=req.k)
    answer = llm.ask(req.query, context)

    return {"answer": answer, "context": context}

@app.post("/rag_query")
async def rag_only(req: QueryRequest, _: str = Depends(verify_api_key)):
    """Debug Endpoint: Returns only the retrieved graph nodes"""
    context = rag.retrieve(req.query, k=req.k)
    return {"query": req.query, "context": context}

@app.post("/langchain_rag", response_model=LangChainResponse)
async def langchain_rag_endpoint(req: QueryRequest, _: str = Depends(verify_api_key)):
    """Alternative Pipeline: Uses LangChain's internal orchestration"""
    answer = langchain_rag.ask(req.query)
    return {"query": req.query, "answer": answer}

# PURPOSE: Main entry point for the CodeAtlas service.