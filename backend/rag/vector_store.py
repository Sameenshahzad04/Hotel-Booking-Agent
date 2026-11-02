import warnings
import logging
from typing import Set
from langchain_core.documents import Document
from langchain_chroma import Chroma
from config import config
from rag.extractor import load_documents
from rag.chunker import split_into_chunks
from rag.embedder import get_embeddings

warnings.filterwarnings("ignore", category=DeprecationWarning)
logging.getLogger("pypdf").setLevel(logging.ERROR)

def _get_indexed_filenames(vectorstore: Chroma) -> Set[str]:
    try:
        results = vectorstore._collection.get(include=["metadatas"])
        filenames = set()
        for meta in results.get("metadatas") or []: 
            if meta and "filename" in meta:
                filenames.add(meta["filename"])
        return filenames
    except Exception:
        return set()

def _load_or_create_chroma(embeddings) -> Chroma:
    return Chroma(
        persist_directory=str(config.CHROMA_DB_DIR),
        embedding_function=embeddings
    )

def sync_corpus() -> Chroma:
    """Syncs documents from Rag_doc into local ChromaDB."""
    embeddings = get_embeddings()
    vectorstore = _load_or_create_chroma(embeddings)

    existing_files = _get_indexed_filenames(vectorstore)
    if existing_files:
        print(f"ℹ️ Already indexed in ChromaDB: {len(existing_files)} file(s).")

    all_docs = load_documents(exclude_filenames=existing_files)
    if not all_docs:
        print("✅ Vector database is already fully up-to-date with Rag_doc.")
        return vectorstore

    print(f"📥 Found {len(all_docs)} new document(s) to ingest. Extracting chunks...")
    chunks = split_into_chunks(all_docs)
    if not chunks:
        print("ℹ️ No new chunks generated.")
        return vectorstore

    lc_documents = [
        Document(page_content=c["text"], metadata=c["metadata"])
        for c in chunks
    ]

    print(f"⚡ Adding {len(lc_documents)} chunks to local ChromaDB...")
    batch_size = 500
    for i in range(0, len(lc_documents), batch_size):
        batch = lc_documents[i:i + batch_size]
        vectorstore.add_documents(batch)

    print("✅ ChromaDB sync completed successfully!")
    return vectorstore

_retriever_cache = None

# def get_retriever():
#     global _retriever_cache
#     if _retriever_cache is None:
#         vectorstore = sync_corpus()
#         if vectorstore:
#             _retriever_cache = vectorstore.as_retriever(
#                 search_kwargs={"k": config.DOCUMENT_SEARCH_TOP_K}
#             )
#     return _retriever_cache

# if __name__ == "__main__":
#     sync_corpus()


def get_retriever():
    global _retriever_cache
    if _retriever_cache is None:
        embeddings = get_embeddings()
        vectorstore = _load_or_create_chroma(embeddings)
        
        # 🔓 Uncomment the line below if you want to run sync_corpus()
        # vectorstore = sync_corpus()
        
        if vectorstore:
            _retriever_cache = vectorstore.as_retriever(
                search_kwargs={"k": config.DOCUMENT_SEARCH_TOP_K}
            )
    return _retriever_cache

if __name__ == "__main__":
    sync_corpus()