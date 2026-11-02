from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import config

class Chunker:
    """Text and Markdown Table Chunker for RAG pipelines."""

    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""]
        )

    def chunk_text(self, text: str) -> List[str]:
        if not text or not text.strip():
            return []
        return self.text_splitter.split_text(text)

    def chunk_table(self, table_markdown: str, table_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not table_markdown:
            return []

        max_chars = config.TABLE_MAX_CHARS
        total_rows = table_info.get("num_rows", 0)

        if len(table_markdown) <= max_chars:
            return [{
                "chunk": table_markdown,
                "chunk_index": 0,
                "row_start": 0,
                "row_end": total_rows,
                "is_full_table": True
            }]

        lines = table_markdown.split("\n")
        if len(lines) < 3:
            return [{
                "chunk": table_markdown,
                "chunk_index": 0,
                "row_start": 0,
                "row_end": total_rows,
                "is_full_table": True
            }]

        headers = lines[:2]
        data_rows = lines[2:]
        header_len = sum(len(line) + 1 for line in headers)

        chunks = []
        i = 0
        overlap = config.TABLE_CHUNK_OVERLAP

        while i < len(data_rows):
            current_chunk = headers.copy()
            current_len = header_len
            row_start = i

            while i < len(data_rows):
                row_len = len(data_rows[i]) + 1
                if current_len + row_len > max_chars and len(current_chunk) > 2:
                    break
                current_chunk.append(data_rows[i])
                current_len += row_len
                i += 1

            row_end = i

            chunks.append({
                "chunk": "\n".join(current_chunk),
                "chunk_index": len(chunks),
                "row_start": row_start,
                "row_end": row_end,
                "is_full_table": False
            })

            if i < len(data_rows):
                i = max(row_start + 1, i - overlap)

        return chunks

    def create_text_chunks_with_metadata(
        self, text: str, doc_id: int, filename: str, file_type: str, category: str = "support"
    ) -> List[Dict[str, Any]]:
        return [
            {
                "text": chunk,
                "metadata": {
                    "doc_id": doc_id,
                    "filename": filename,
                    "file_type": file_type,
                    "category": category,
                    "chunk_type": config.CHUNK_TYPE_TEXT,
                    "chunk_index": idx
                }
            }
            for idx, chunk in enumerate(self.chunk_text(text))
        ]

    def create_table_chunks_with_metadata(
        self, tables: List[Dict[str, Any]], doc_id: int, filename: str, file_type: str, category: str = "support"
    ) -> List[Dict[str, Any]]:
        result = []
        chunk_counter = 0

        for table in tables:
            # Prepend the heading/context so the embedding captures semantic meaning
            # e.g. "Table from: Room pricing rates" instead of bare markdown
            heading = table.get("heading", "")
            table_chunks = self.chunk_table(table.get("markdown", ""), table)
            for chunk_info in table_chunks:
                # Prefix heading so vector search connects "price" → "Nightly Rate (PKR)"
                text_with_context = (
                    f"{heading}\n\n{chunk_info['chunk']}" if heading else chunk_info["chunk"]
                )
                result.append({
                    "text": text_with_context,
                    "metadata": {
                        "doc_id": doc_id,
                        "filename": filename,
                        "file_type": file_type,
                        "category": category,
                        "chunk_type": config.CHUNK_TYPE_TABLE,
                        "chunk_index": chunk_counter,
                        "table_page": table.get("page", 0),
                        "table_index": table.get("table_index", 0),
                        "row_start": chunk_info["row_start"],
                        "row_end": chunk_info["row_end"],
                        "is_full_table": chunk_info["is_full_table"]
                    }
                })
                chunk_counter += 1

        return result

def split_into_chunks(documents_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not documents_data:
        return []

    chunker = Chunker()
    all_chunks = []

    for doc in documents_data:
        doc_category = doc.get("category", "support")
        if doc.get("text"):
            text_chunks = chunker.create_text_chunks_with_metadata(
                text=doc["text"],
                doc_id=doc["doc_id"],
                filename=doc["filename"],
                file_type=doc["file_type"],
                category=doc_category
            )
            all_chunks.extend(text_chunks)
            
        if doc.get("tables"):
            table_chunks = chunker.create_table_chunks_with_metadata(
                tables=doc["tables"],
                doc_id=doc["doc_id"],
                filename=doc["filename"],
                file_type=doc["file_type"],
                category=doc_category
            )
            all_chunks.extend(table_chunks)

    return all_chunks
