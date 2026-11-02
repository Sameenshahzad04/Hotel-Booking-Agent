import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

class Config:
    # -------------------------------------------------------------------------
    # Database Settings
    # -------------------------------------------------------------------------
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "pc_lahore_db")
    
    DATABASE_URL = os.getenv(
        "DATABASE_URL", 
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    # -------------------------------------------------------------------------
    # OpenRouter Free LLM Settings
    # -------------------------------------------------------------------------
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_BASE_URL = os.getenv("URL")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")
    SYSTEM_MESSAGE = os.getenv(
        "SYSTEM_MESSAGE", 
        "You are the official AI concierge for Pearl Continental (PC) Hotel Lahore."
    )

    # -------------------------------------------------------------------------
    # Hotel Business Rules & Constants
    # -------------------------------------------------------------------------
    SHOW_COST_ON = os.getenv("SHOW_COST_ON", "book,checkout").split(",")
    HOLD_EXPIRY_HOURS = int(os.getenv("HOLD_EXPIRY_HOURS", "2"))
    CHECK_IN_TIME = os.getenv("CHECK_IN_TIME", "14:00")
    CHECK_OUT_TIME = os.getenv("CHECK_OUT_TIME", "12:00")
    MAX_AGENT_ITERATIONS = 5
    AGENT_TIMEOUT = 60

    # -------------------------------------------------------------------------
    # Free SMTP & Email Delivery Settings (Gmail App Password or Free SMTP)
    # -------------------------------------------------------------------------
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USER", "concierge@pchotels.com"))
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Pearl Continental Hotel Lahore")
    OTP_EXPIRY_MINUTES = int(os.getenv("OTP_EXPIRY_MINUTES", "5"))

    # -------------------------------------------------------------------------
    # RAG Pipeline Configuration (Anchored to Root Project Directory)
    # -------------------------------------------------------------------------
    _BASE_DIR = Path(__file__).resolve().parent.parent
    CORPUS_DIR = _BASE_DIR / "Rag_doc"
    CHROMA_DB_DIR = _BASE_DIR / "chroma_db"
    MODELS_DIR = _BASE_DIR / "local_models"
    
    EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    CHUNK_SIZE = 400
    CHUNK_OVERLAP = 50
    TABLE_MAX_CHARS = 1000
    TABLE_CHUNK_OVERLAP = 2
    CHUNK_TYPE_TEXT = "text"
    CHUNK_TYPE_TABLE = "table"
    DOCUMENT_SEARCH_TOP_K = 6

    # Ensure directories exist
    CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

config = Config()

def get_llm():
    """Initializes and returns the  model routed through OpenRouter."""
    if not config.OPENROUTER_API_KEY:
        print("⚠️ Warning: OPENROUTER_API_KEY is not set in .env.")
    
    return ChatOpenAI(
        base_url=config.OPENROUTER_BASE_URL,
        api_key=config.OPENROUTER_API_KEY,
        model=config.OPENROUTER_MODEL,
        temperature=0.2,
        default_headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "PCLahoreHotelAgent"
        }
    )
