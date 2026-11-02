from fastapi import APIRouter, HTTPException
from schema.rag_schema import RAGSearchRequest
from rag.vector_store import get_retriever, sync_corpus

router = APIRouter(prefix="/rag", tags=["RAG & Knowledge Base"])

@router.post("/sync")
def trigger_rag_sync():
    """Triggers ingestion and sync of Rag_doc into ChromaDB."""
    try:
        sync_corpus()
        return {"success": True, "message": "Rag_doc corpus synced successfully into ChromaDB!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG Sync failed: {str(e)}")

@router.post("/search")
def search_knowledge_base(req: RAGSearchRequest):
    """Searches PC Lahore policies, SOPs, and knowledge base."""
    retriever = get_retriever()
    if not retriever:
        raise HTTPException(status_code=500, detail="Vector store not initialized.")
    docs = retriever.invoke(req.query)
    return {
        "query": req.query,
        "results": [
            {
                "content": doc.page_content,
                "metadata": doc.metadata
            }
            for doc in docs
        ]
    }
