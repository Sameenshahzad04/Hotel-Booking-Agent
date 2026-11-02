from pydantic import BaseModel

class RAGSearchRequest(BaseModel):
    query: str
