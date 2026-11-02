from langchain_huggingface import HuggingFaceEmbeddings
from config import config

class EmbedderSingleton:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            try:
                cls._instance.model = HuggingFaceEmbeddings(
                    model_name=config.EMBEDDING_MODEL,
                    cache_folder=str(config.MODELS_DIR),
                    model_kwargs={"local_files_only": True}
                )
            except Exception:
                cls._instance.model = HuggingFaceEmbeddings(
                    model_name=config.EMBEDDING_MODEL,
                    cache_folder=str(config.MODELS_DIR)
                )
        return cls._instance

def get_embeddings():
    """Returns the globally cached embedding model instance."""
    return EmbedderSingleton().model
